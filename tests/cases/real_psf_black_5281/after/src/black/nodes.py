
def prev_siblings_are(node: LN | None, tokens: list[NodeType | None]) -> bool:
    """Return if the `node` and its previous siblings match types against the provided
    list of tokens; the provided `node` has its type matched against the last element in
    the list.  `None` can be used as the first element to declare that the start of the
    list is anchored at the start of its parent's children."""
    if not tokens:
