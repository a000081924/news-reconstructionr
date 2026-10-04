from html import escape
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring

from newsrec.domain.page import Page


def export_page(page: Page, format: str) -> tuple[str, str]:
    if format == "html":
        blocks = "\n".join(f'<section data-block="{b.id}" style="writing-mode:vertical-rl;white-space:pre-wrap">{escape(b.text)}</section>' for b in page.blocks)
        return f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>Newspaper transcription</title><main>{blocks}</main></html>', "text/html"
    if format == "alto":
        root = Element("alto", xmlns="http://www.loc.gov/standards/alto/ns-v4#")
        description = SubElement(root, "Description")
        SubElement(description, "MeasurementUnit").text = "pixel"
        source = SubElement(description, "sourceImageInformation")
        SubElement(source, "fileName").text = page.image
        layout = SubElement(root, "Layout")
        node = SubElement(layout, "Page", ID="page_1", PHYSICAL_IMG_NR="1", WIDTH=str(page.width), HEIGHT=str(page.height))
        space = SubElement(node, "PrintSpace", HPOS="0", VPOS="0", WIDTH=str(page.width), HEIGHT=str(page.height))
        for block in page.blocks:
            group = SubElement(space, "TextBlock", ID=f"block_{block.id}", **_alto_box(block.bbox))
            for index, line in enumerate(block.lines or [block]):
                textline = SubElement(group, "TextLine", ID=f"line_{block.id}_{index}", **_alto_box(line.bbox))
                SubElement(textline, "String", CONTENT=line.text, **_alto_box(line.bbox))
    elif format == "page-xml":
        root = Element("PcGts", xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15")
        metadata = SubElement(root, "Metadata")
        SubElement(metadata, "Creator").text = "newsrec"
        # Metadata describes this export, not the historical scan date.
        exported_at = datetime.now(timezone.utc).isoformat()
        for tag in ("Created", "LastChange"):
            SubElement(metadata, tag).text = exported_at
        node = SubElement(root, "Page", imageFilename=page.image, imageWidth=str(page.width), imageHeight=str(page.height))
        reading = SubElement(SubElement(node, "ReadingOrder"), "OrderedGroup", id="reading_order")
        for order, block in enumerate(page.blocks):
            SubElement(reading, "RegionRefIndexed", index=str(order), regionRef=f"block_{block.id}")
            region = SubElement(node, "TextRegion", id=f"block_{block.id}")
            SubElement(region, "Coords", points=_points(block.bbox))
            for index, line in enumerate(block.lines):
                textline = SubElement(region, "TextLine", id=f"line_{block.id}_{index}")
                SubElement(textline, "Coords", points=_points(line.bbox))
                SubElement(SubElement(textline, "TextEquiv"), "Unicode").text = line.text
            SubElement(SubElement(region, "TextEquiv"), "Unicode").text = block.text
    else:
        raise ValueError("unknown export format")
    return tostring(root, encoding="unicode", xml_declaration=True), "application/xml"


def _alto_box(box):
    return {"HPOS": str(round(box.x1)), "VPOS": str(round(box.y1)),
            "WIDTH": str(round(box.x2 - box.x1)), "HEIGHT": str(round(box.y2 - box.y1))}


def _points(box):
    return " ".join(f"{round(x)},{round(y)}" for x, y in [(box.x1, box.y1), (box.x2, box.y1), (box.x2, box.y2), (box.x1, box.y2)])
