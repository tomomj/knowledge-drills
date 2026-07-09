from __future__ import annotations

from collections.abc import Callable, Iterable
from contextvars import ContextVar
from copy import deepcopy
from typing import Protocol, TypeVar, cast

from google.api_core import exceptions as google_exceptions
from google.cloud import firestore
from google.cloud.firestore_v1 import Client, DocumentReference, DocumentSnapshot, Transaction
from google.cloud.firestore_v1.base_query import FieldFilter

DocumentData = dict[str, object]
T = TypeVar("T")


class DocumentAlreadyExists(Exception):
    pass


class DocumentNotFound(Exception):
    pass


class FirestoreClient(Protocol):
    def create_document(self, collection: str, document_id: str, data: DocumentData) -> None: ...

    def set_document(self, collection: str, document_id: str, data: DocumentData) -> None: ...

    def get_document(self, collection: str, document_id: str) -> DocumentData | None: ...

    def update_document(self, collection: str, document_id: str, data: DocumentData) -> None: ...

    def delete_document(self, collection: str, document_id: str) -> None: ...

    def list_documents(self, collection: str) -> list[DocumentData]: ...

    def list_documents_by_field(
        self,
        collection: str,
        field_name: str,
        field_value: object,
    ) -> list[DocumentData]: ...

    def run_transaction(self, callback: Callable[[], T]) -> T: ...


class InMemoryFirestoreClient:
    def __init__(self) -> None:
        self._collections: dict[str, dict[str, DocumentData]] = {}
        self.transaction_count = 0

    def create_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        collection_data = self._collections.setdefault(collection, {})
        if document_id in collection_data:
            raise DocumentAlreadyExists(f"{collection}/{document_id} already exists")
        collection_data[document_id] = deepcopy(data)

    def set_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        self._collections.setdefault(collection, {})[document_id] = deepcopy(data)

    def get_document(self, collection: str, document_id: str) -> DocumentData | None:
        document = self._collections.get(collection, {}).get(document_id)
        if document is None:
            return None
        return deepcopy(document)

    def update_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        collection_data = self._collections.setdefault(collection, {})
        if document_id not in collection_data:
            raise DocumentNotFound(f"{collection}/{document_id} was not found")
        collection_data[document_id].update(deepcopy(data))

    def delete_document(self, collection: str, document_id: str) -> None:
        self._collections.setdefault(collection, {}).pop(document_id, None)

    def list_documents(self, collection: str) -> list[DocumentData]:
        return [deepcopy(document) for document in self._collections.get(collection, {}).values()]

    def list_documents_by_field(
        self,
        collection: str,
        field_name: str,
        field_value: object,
    ) -> list[DocumentData]:
        return [
            deepcopy(document)
            for document in self._collections.get(collection, {}).values()
            if document.get(field_name) == field_value
        ]

    def run_transaction(self, callback: Callable[[], T]) -> T:
        self.transaction_count += 1
        return callback()


class GoogleFirestoreClient:
    def __init__(
        self,
        *,
        project: str | None = None,
        database: str | None = None,
        client: Client | None = None,
    ) -> None:
        self._client = (
            client if client is not None else firestore.Client(project=project, database=database)
        )
        self._active_transaction: ContextVar[Transaction | None] = ContextVar(
            "active_firestore_transaction",
            default=None,
        )

    def create_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        reference = self._document(collection, document_id)
        try:
            transaction = self._active_transaction.get()
            if transaction is None:
                reference.create(deepcopy(data))
            else:
                transaction.create(reference, deepcopy(data))
        except google_exceptions.Conflict as exc:
            raise DocumentAlreadyExists(f"{collection}/{document_id} already exists") from exc

    def set_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        reference = self._document(collection, document_id)
        transaction = self._active_transaction.get()
        if transaction is None:
            reference.set(deepcopy(data))
        else:
            transaction.set(reference, deepcopy(data))

    def get_document(self, collection: str, document_id: str) -> DocumentData | None:
        reference = self._document(collection, document_id)
        transaction = self._active_transaction.get()
        snapshot = reference.get() if transaction is None else next(transaction.get(reference))
        if not snapshot.exists:
            return None
        return self._snapshot_to_document(snapshot.to_dict())

    def update_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        reference = self._document(collection, document_id)
        try:
            transaction = self._active_transaction.get()
            if transaction is None:
                reference.update(deepcopy(data))
            else:
                transaction.update(reference, deepcopy(data))
        except google_exceptions.NotFound as exc:
            raise DocumentNotFound(f"{collection}/{document_id} was not found") from exc

    def delete_document(self, collection: str, document_id: str) -> None:
        reference = self._document(collection, document_id)
        transaction = self._active_transaction.get()
        if transaction is None:
            reference.delete()
        else:
            transaction.delete(reference)

    def list_documents(self, collection: str) -> list[DocumentData]:
        snapshots = self._client.collection(collection).stream()
        return [self._snapshot_to_document(snapshot.to_dict()) for snapshot in snapshots]

    def list_documents_by_field(
        self,
        collection: str,
        field_name: str,
        field_value: object,
    ) -> list[DocumentData]:
        query = self._client.collection(collection).where(
            filter=FieldFilter(field_name, "==", field_value)
        )
        transaction = self._active_transaction.get()
        snapshots = cast(
            Iterable[DocumentSnapshot],
            query.stream() if transaction is None else transaction.get(query),
        )
        return [self._snapshot_to_document(snapshot.to_dict()) for snapshot in snapshots]

    def run_transaction(self, callback: Callable[[], T]) -> T:
        transaction = self._client.transaction()

        @firestore.transactional
        def run(active_transaction: Transaction) -> T:
            token = self._active_transaction.set(active_transaction)
            try:
                return callback()
            finally:
                self._active_transaction.reset(token)

        return cast(T, run(transaction))

    def _document(self, collection: str, document_id: str) -> DocumentReference:
        return self._client.collection(collection).document(document_id)

    def _snapshot_to_document(self, data: DocumentData | None) -> DocumentData:
        if data is None:
            return {}
        return deepcopy(data)
