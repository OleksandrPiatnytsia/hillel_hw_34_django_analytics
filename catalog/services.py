from .models import Book, Category


def upsert_book(snapshot):
    """Create or update the book of an order line, with its categories.

    snapshot: the validated "book" of an event (events/contract.py).
    The newest snapshot wins: a renamed book or a changed category list in
    the bookstore shows up here with the next order of that book.
    """
    book, _created = Book.objects.update_or_create(
        source_id=snapshot["id"],
        defaults={
            "title": snapshot["title"],
            "author": snapshot["author"],
            "publisher": snapshot["publisher"],
            "language": snapshot["language"],
        },
    )
    categories = [
        Category.objects.update_or_create(
            source_id=category["id"], defaults={"name": category["name"]}
        )[0]
        for category in snapshot["categories"]
    ]
    # set(): exactly these categories; a removed one is unlinked
    book.categories.set(categories)
    return book
