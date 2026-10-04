from newsrec.domain.page import Page


def apply(page: Page, edits: list[dict]) -> Page:
    result = Page.from_dict(page.to_dict())
    blocks = {b.id: b for b in result.blocks}
    seen = set()
    for edit in edits:
        key = (edit["block_id"], edit["line_index"])
        if key in seen:
            raise ValueError("duplicate correction")
        seen.add(key)
        block = blocks.get(key[0])
        if block is None:
            raise ValueError("unknown block")
        index = key[1]
        if not isinstance(edit["text"], str):
            raise ValueError("correction must be text")
        if index == -1 and not block.lines:
            block.text = edit["text"]
        elif 0 <= index < len(block.lines):
            block.lines[index].text = edit["text"]
            block.text = "\n".join(line.text for line in block.lines)
        else:
            raise ValueError("invalid line index; use -1 only for blocks without lines")
    return result


def corrected(repo, page_id, engine):
    return apply(repo.get_page(page_id, engine), repo.get_corrections(page_id, engine))


def save(repo, page_id, engine, edits):
    result = apply(repo.get_page(page_id, engine), edits)
    repo.replace_corrections(page_id, engine, edits)
    return result
