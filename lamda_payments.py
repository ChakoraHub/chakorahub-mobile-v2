def lambda_handler(event, context):
  body = event
    if isinstance(event, dict) and "body" in event:
        try:
            # Minimal inline JSON parsing without 'import json'
            b = event["body"]
            # Strip braces and manually parse (for demo)
            if isinstance(b, str):
                b = b.strip()
                if b.startswith("{") and b.endswith("}"):
                    b = b[1:-1]
                parts = [p.strip() for p in b.split(",") if ":" in p]
                body = {}
                for p in parts:
                    k, v = p.split(":", 1)
                    k = k.strip().replace('"', "").replace("'", "")
                    v = v.strip().replace('"', "").replace("'", "")
                    body[k] = v
            else:
                body = b
        except Exception as e:
            return {
                "statusCode": 400,
                "body": "{'error': 'Invalid JSON body'}"
            }

    # Validate required fields
    required_fields = ["upi_id", "phone", "course", "payment"]
    missing = []
    for f in required_fields:
        if f not in body or body[f] == "":
            missing.append(f)

    if missing:
        return {
            "statusCode": 400,
            "body": "{'error': 'Missing fields: " + ", ".join(missing) + "'}"
        }

    # Simulate database insert
    upi_id = body["upi_id"]
    phone = body["phone"]
    course = body["course"]
    payment = body["payment"]

    # Create fake insert confirmation message
    message = (
        "Billing entry stored successfully. "
        "UPI: " + upi_id + ", Phone: " + phone +
        ", Course: " + course + ", Payment: " + payment
    )

    # Return AWS Lambda-style response
    return {
        "statusCode": 200,
        "body": "{'message': '" + message + "'}"
    }