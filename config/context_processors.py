from django.conf import settings


def version(request):
    """Adds the version of the service to every template: the footer of base.html.

    Registered in settings.TEMPLATES["OPTIONS"]["context_processors"].
    app_version: "0.1.0"; app_commit: the full SHA or "" (config/version.py);
    app_commit_url: the commit on GitHub, "" without a commit;
    bookstore_repository_url: the other half of the homework.
    """
    commit = settings.APP_COMMIT
    return {
        "app_version": settings.APP_VERSION,
        "app_commit": commit,
        "app_commit_url": f"{settings.APP_REPOSITORY_URL}/commit/{commit}" if commit else "",
        "bookstore_repository_url": settings.BOOKSTORE_REPOSITORY_URL,
    }
