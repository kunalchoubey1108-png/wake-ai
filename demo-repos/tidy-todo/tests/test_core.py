from tidy_todo import TodoList


def test_add_and_count():
    tl = TodoList()
    tl.add("buy milk")
    tl.add("write tests")
    assert tl.count() == 2


def test_complete_and_pending():
    tl = TodoList()
    tl.add("a")
    tl.add("b")
    tl.complete(0)
    pending = tl.pending()
    assert len(pending) == 1
    assert pending[0].title == "b"
