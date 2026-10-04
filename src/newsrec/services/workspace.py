from hashlib import sha256

from newsrec.repository.db import Repository
from newsrec.services import corrections
from newsrec.services.ingestion import ingest
from newsrec.services.export import export_page


class Workspace:
    def __init__(self, root):
        self.repo = Repository(root)

    def upload(self, name, content):
        image, thumbnail = ingest(content)
        return self.repo.create_document(name, image, thumbnail, sha256(image).hexdigest())

    def documents(self):
        return self.repo.documents()

    def document(self, document_id):
        for document in self.documents():
            if document["id"] == document_id:
                return document
        raise KeyError(document_id)

    def delete_document(self, document_id):
        self.repo.delete_document(document_id)

    def image(self, page_id, thumbnail=False):
        ref = self.repo.page_ref(page_id)
        return self.repo.blob_path(ref["thumbnail" if thumbnail else "image"])

    def page(self, page_id, engine):
        return corrections.corrected(self.repo, page_id, engine).to_dict()

    def edits(self, page_id, engine):
        self.repo.get_page(page_id, engine)
        return self.repo.get_corrections(page_id, engine)

    def save_edits(self, page_id, engine, edits):
        return corrections.save(self.repo, page_id, engine, edits).to_dict()

    def export(self, page_id, engine, format):
        return export_page(corrections.corrected(self.repo, page_id, engine), format)

    def job(self, job_id):
        return self.repo.job(job_id)
