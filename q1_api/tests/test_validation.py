from app.validation import parse_csv


def test_issue_date_before_dob_is_rejected():
    text = (
        "case_ref,applicant_name,id_number,dob,issue_date,image_ref\n"
        "A,Alice,TEST-ID-1,2000-01-02,2000-01-01,scan.jpg\n"
    )

    accepted, rejected = parse_csv(text.encode("utf-8"))

    assert len(accepted) == 0
    assert len(rejected) == 1
    assert (
        "issue_date must not be earlier than dob"
        in rejected[0]["reasons"]
    )

def test_issue_date_and_dob_can_same():
    text = (
        "case_ref,applicant_name,id_number,dob,issue_date,image_ref\n"
        "A,Alice,TEST-ID-1,2000-01-01,2000-01-01,scan.jpg\n"
    )

    accepted, rejected = parse_csv(text.encode("utf-8"))

    assert len(accepted) == 1
    assert len(rejected) == 0
    assert accepted[0]["dob"] == accepted[0]["issue_date"] == "2000-01-01"

def test_invalid_date_does_not_block_valid_row():
    text = (
        "case_ref,applicant_name,id_number,dob,issue_date,image_ref\n"
        "A,Alice,TEST-ID-1,2000-01-01,2020-01-01,a.jpg\n"
        "B,Bob,TEST-ID-2,2000-02-30,2020-01-01,b.jpg\n"
    )

    accepted, rejected = parse_csv(text.encode("utf-8"))
    assert len(accepted) == 1
    assert len(rejected) == 1

    assert accepted[0]["case_ref"] == "A"
    assert rejected[0]["case_ref"] == "B"
    assert rejected[0]["reasons"] == ['dob must be a valid YYYY-MM-DD date']
    
    #assert "dob must be a valid YYYY-MM-DD date" in rejected[0]["reasons"]
