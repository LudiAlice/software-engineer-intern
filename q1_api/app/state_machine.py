"""All staff review transitions are defined here, including terminal rejections."""
TRANSITIONS = {
    ("ocr_done", 1, "approve"): "stage1_approved",
    ("ocr_done", 1, "reject"): "stage1_rejected",
    ("stage1_approved", 2, "approve"): "stage2_approved",
    ("stage1_approved", 2, "reject"): "stage2_rejected",
}
STATUSES = (
    "pending", "ocr_done", "ocr_failed", "stage1_approved", "stage1_rejected",
    "stage2_approved", "stage2_rejected", "exported",
)


def next_status(current, stage, decision):
    try:
        return TRANSITIONS[(current, stage, decision)]
    except KeyError:
        raise ValueError(f"Cannot {decision} stage {stage} from {current}") from None
