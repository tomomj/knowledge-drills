from app.repositories.firestore_client import FirestoreClient
from app.schemas import UserProfile


class UserRepository:
    collection = "users"

    def __init__(self, client: FirestoreClient) -> None:
        self._client = client

    def get(self, uid: str) -> UserProfile | None:
        document = self._client.get_document(self.collection, uid)
        if document is None:
            return None
        return UserProfile.model_validate(document)

    def upsert(self, profile: UserProfile) -> None:
        self._client.set_document(
            self.collection,
            profile.uid,
            profile.model_dump(mode="json", by_alias=True),
        )
