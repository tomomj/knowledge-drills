from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import pytest
from google.api_core import exceptions as google_exceptions
from google.cloud.firestore_v1 import Client
from google.cloud.firestore_v1.base_query import FieldFilter

from app.repositories.firestore_client import (
    DocumentAlreadyExists,
    DocumentData,
    DocumentNotFound,
    GoogleFirestoreClient,
)


class FakeSnapshot:
    def __init__(self, data: DocumentData | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> DocumentData | None:
        return self._data


class FakeDocument:
    def __init__(self, collection: FakeCollection, document_id: str) -> None:
        self._collection = collection
        self._document_id = document_id

    def create(self, data: DocumentData) -> None:
        if self._document_id in self._collection.documents:
            raise google_exceptions.Conflict("already exists")  # type: ignore[no-untyped-call]
        self._collection.documents[self._document_id] = dict(data)

    def set(self, data: DocumentData) -> None:
        self._collection.documents[self._document_id] = dict(data)

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self._collection.documents.get(self._document_id))

    def update(self, data: DocumentData) -> None:
        if self._document_id not in self._collection.documents:
            raise google_exceptions.NotFound("not found")  # type: ignore[no-untyped-call]
        self._collection.documents[self._document_id].update(data)

    def delete(self) -> None:
        self._collection.documents.pop(self._document_id, None)


class FakeQuery:
    def __init__(self, collection: FakeCollection, field_name: str, field_value: object) -> None:
        self._collection = collection
        self._field_name = field_name
        self._field_value = field_value

    def stream(self) -> Iterator[FakeSnapshot]:
        for document in self._collection.documents.values():
            if document.get(self._field_name) == self._field_value:
                yield FakeSnapshot(document)


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, DocumentData] = {}

    def document(self, document_id: str) -> FakeDocument:
        return FakeDocument(self, document_id)

    def stream(self) -> Iterator[FakeSnapshot]:
        for document in self.documents.values():
            yield FakeSnapshot(document)

    def where(self, *, filter: object) -> FakeQuery:
        field_filter = cast(FieldFilter, filter)
        return FakeQuery(
            self,
            field_filter.field_path,
            field_filter.value,
        )


class FakeTransaction:
    def __init__(self) -> None:
        self.created = 0
        self.updated = 0

    def create(self, reference: FakeDocument, data: DocumentData) -> None:
        self.created += 1
        reference.create(data)

    def set(self, reference: FakeDocument, data: DocumentData) -> None:
        reference.set(data)

    def update(self, reference: FakeDocument, data: DocumentData) -> None:
        self.updated += 1
        reference.update(data)

    def delete(self, reference: FakeDocument) -> None:
        reference.delete()

    def get(self, reference_or_query: FakeDocument | FakeQuery) -> Iterator[FakeSnapshot]:
        if isinstance(reference_or_query, FakeDocument):
            yield reference_or_query.get()
            return
        yield from reference_or_query.stream()


class FakeFirestoreSdk:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.latest_transaction: FakeTransaction | None = None

    def collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    def transaction(self) -> FakeTransaction:
        self.latest_transaction = FakeTransaction()
        return self.latest_transaction


def _client(sdk: FakeFirestoreSdk) -> GoogleFirestoreClient:
    return GoogleFirestoreClient(client=cast(Client, sdk))


def test_google_firestore_client_maps_document_operations() -> None:
    sdk = FakeFirestoreSdk()
    client = _client(sdk)

    client.create_document("courses", "course-1", {"id": "course-1", "courseId": "c1"})
    client.set_document("courses", "course-2", {"id": "course-2", "courseId": "c1"})
    client.update_document("courses", "course-2", {"title": "更新"})
    client.delete_document("courses", "course-1")
    client.delete_document("courses", "missing")

    assert client.get_document("courses", "course-2") == {
        "id": "course-2",
        "courseId": "c1",
        "title": "更新",
    }
    assert [document["id"] for document in client.list_documents("courses")] == [
        "course-2",
    ]
    course_documents = client.list_documents_by_field("courses", "courseId", "c1")
    assert [document["id"] for document in course_documents] == [
        "course-2",
    ]


def test_google_firestore_client_maps_sdk_exceptions() -> None:
    client = _client(FakeFirestoreSdk())
    client.create_document("courses", "course-1", {"id": "course-1"})

    with pytest.raises(DocumentAlreadyExists):
        client.create_document("courses", "course-1", {"id": "course-1"})

    with pytest.raises(DocumentNotFound):
        client.update_document("courses", "missing", {"title": "更新"})


def test_google_firestore_client_uses_transaction_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.repositories.firestore_client.firestore.transactional",
        lambda callback: callback,
    )
    sdk = FakeFirestoreSdk()
    client = _client(sdk)
    client.create_document("patches", "patch-1", {"id": "patch-1", "status": "proposed"})

    def callback() -> str:
        assert client.get_document("patches", "patch-1") is not None
        client.update_document("patches", "patch-1", {"status": "applied"})
        return "ok"

    assert client.run_transaction(callback) == "ok"
    assert sdk.latest_transaction is not None
    assert sdk.latest_transaction.updated == 1
    assert client.get_document("patches", "patch-1") == {
        "id": "patch-1",
        "status": "applied",
    }
