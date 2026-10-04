"""Transparent, sample-scoped OCR metrics; never equate character count with accuracy."""
import unicodedata


def normalize_text(text):
    return "".join(c for c in unicodedata.normalize("NFC", text) if not c.isspace())


def edit_distance(reference, prediction):
    previous = list(range(len(prediction) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(prediction, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def cer(reference, prediction):
    reference, prediction = normalize_text(reference), normalize_text(prediction)
    if not reference:
        raise ValueError("CER requires nonempty ground truth")
    return edit_distance(reference, prediction) / len(reference)


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0]) * (a[3]-a[1]) + (b[2]-b[0]) * (b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0


def evaluate(page, samples, threshold=0.5):
    """One-to-one IoU line matching. Missing detections count as full deletions.

    Reports micro CER across sampled reference lines. Extra detections outside the
    sample are not scored, so this is not a full-page hallucination/precision metric.
    Punctuation and script variants are scored literally; whitespace is ignored.
    """
    predictions = [line for block in page.blocks for line in block.lines]
    edges = sorted(((iou(s["bbox"], p.bbox.to_list()), i, j)
                    for i, s in enumerate(samples) for j, p in enumerate(predictions)), reverse=True)
    matches, used = {}, set()
    for overlap, i, j in edges:
        if overlap < threshold:
            break
        if i not in matches and j not in used:
            matches[i] = j
            used.add(j)
    errors = chars = 0
    details = []
    for i, sample in enumerate(samples):
        ref = normalize_text(sample["text"])
        if not ref:
            raise ValueError("empty ground truth line")
        predicted = predictions[matches[i]].text if i in matches else ""
        distance = edit_distance(ref, normalize_text(predicted))
        chars += len(ref)
        errors += distance
        details.append({"sample": sample["id"], "reference": sample["text"], "prediction": predicted, "errors": distance, "matched": i in matches})
    if not chars:
        raise ValueError("no ground truth samples")
    texts = "".join(p.text for p in predictions)
    probes = "国华军务台"
    return {"cer": errors / chars, "errors": errors, "reference_characters": chars,
            "line_recall_iou_0_5": len(matches) / len(samples),
            "matched_lines": len(matches), "sampled_lines": len(samples),
            "simplified_probe_counts": {c: texts.count(c) for c in probes}, "details": details}
