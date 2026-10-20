import assistant


class InMemoryVectorStore:
    def __init__(self):
        self.documents = {}

    def get(self, where=None):
        records = [
            (identifier, document)
            for identifier, document in self.documents.items()
            if where is None or document.metadata["source"] == where["source"]
        ]
        return {
            "ids": [identifier for identifier, _ in records],
            "metadatas": [document.metadata for _, document in records],
        }

    def delete(self, ids):
        for identifier in ids:
            self.documents.pop(identifier, None)

    def add_documents(self, documents, ids):
        self.documents.update(zip(ids, documents))


def test_source_index_is_idempotent_and_replaces_changed_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "DOCUMENTS_DIR", str(tmp_path))
    source = tmp_path / "procedure.md"
    store = InMemoryVectorStore()

    source.write_text("First version of the recovery procedure.", encoding="utf-8")
    assert assistant._sync_source(store, str(source)) == 1
    first_ids = set(store.documents)
    assert len(first_ids) == 1
    assert assistant._sync_source(store, str(source)) == 1
    assert set(store.documents) == first_ids

    source.write_text("Updated procedure with verified transaction recovery.", encoding="utf-8")
    assert assistant._sync_source(store, str(source)) == 1
    assert len(store.documents) == 1
    assert set(store.documents).isdisjoint(first_ids)
    assert next(iter(store.documents.values())).page_content.startswith("Updated procedure")


def test_deleted_markdown_sources_are_removed_from_the_index(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "DOCUMENTS_DIR", str(tmp_path))
    source = tmp_path / "old.md"
    source.write_text("Old procedure.", encoding="utf-8")
    store = InMemoryVectorStore()
    assistant._sync_source(store, str(source))
    assert store.documents

    assistant._remove_deleted_sources(store, [])

    assert not store.documents
