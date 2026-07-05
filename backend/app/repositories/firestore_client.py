from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import TypeVar

DocumentData = dict[str, object]
T = TypeVar("T")


class DocumentAlreadyExists(Exception):
    pass


class DocumentNotFound(Exception):
    pass


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
