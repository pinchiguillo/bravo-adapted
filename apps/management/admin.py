import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.template.response import TemplateResponse
from django.urls import path

TEXT_DOCUMENT_EXTENSIONS = {
    ".html",
    ".json",
    ".md",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
}


def _get_legal_documents_root() -> Path:
    return Path(settings.LEGAL_DOCUMENTS_ROOT).resolve()


def _resolve_legal_documents_path(raw_path: str) -> Path:
    root = _get_legal_documents_root()
    relative_path = Path(raw_path or "")
    resolved_path = (root / relative_path).resolve()
    try:
        resolved_path.relative_to(root)
    except ValueError as exc:
        raise Http404("Document not found.") from exc
    return resolved_path


def legal_documents_browser_view(request):
    current_path = request.GET.get("path", "").strip()
    root = _get_legal_documents_root()
    target = _resolve_legal_documents_path(current_path)

    if not root.exists():
        context = {
            **admin.site.each_context(request),
            "title": "Documentos legales",
            "root_exists": False,
            "root_path": str(root),
            "current_path": "",
            "is_file": False,
            "entries": [],
        }
        return TemplateResponse(request, "admin/legal_documents_browser.html", context)

    if not target.exists():
        raise Http404("Document not found.")

    if target.is_file():
        if target.suffix.lower() in TEXT_DOCUMENT_EXTENSIONS:
            content = target.read_text(encoding="utf-8", errors="replace")
            context = {
                **admin.site.each_context(request),
                "title": "Documentos legales",
                "root_exists": True,
                "root_path": str(root),
                "current_path": current_path,
                "current_name": target.name,
                "parent_path": target.parent.relative_to(root).as_posix(),
                "is_file": True,
                "is_text_file": True,
                "file_content": content,
            }
            return TemplateResponse(request, "admin/legal_documents_browser.html", context)

        content_type, _ = mimetypes.guess_type(target.name)
        return FileResponse(
            target.open("rb"),
            content_type=content_type or "application/octet-stream",
            filename=target.name,
        )

    entries = []
    for child in sorted(target.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        relative_child = child.relative_to(root).as_posix()
        entries.append(
            {
                "name": child.name,
                "path": relative_child,
                "is_dir": child.is_dir(),
            }
        )

    relative_current = target.relative_to(root).as_posix()
    parent_path = ""
    if target != root:
        parent_path = target.parent.relative_to(root).as_posix()

    context = {
        **admin.site.each_context(request),
        "title": "Documentos legales",
        "root_exists": True,
        "root_path": str(root),
        "current_path": relative_current,
        "current_name": target.name,
        "parent_path": parent_path,
        "is_file": False,
        "entries": entries,
    }
    return TemplateResponse(request, "admin/legal_documents_browser.html", context)


original_get_urls = admin.site.get_urls


def get_admin_urls():
    custom_urls = [
        path(
            "legal-documents/",
            admin.site.admin_view(legal_documents_browser_view),
            name="legal-documents-browser",
        ),
    ]
    return custom_urls + original_get_urls()


admin.site.get_urls = get_admin_urls
admin.site.index_template = "admin/custom_index.html"
