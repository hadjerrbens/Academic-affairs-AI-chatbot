import base64, hashlib
salt = base64.b64decode("7c5rmCwOmh5ehjB1q+5csA==")
expected = base64.b64decode("qHTTAA/5NAT3ngo5v+y6pY3VbEXHQE7ak6F9pkwFnxk=")
print(hashlib.scrypt(b"test1234", salt=salt, n=16384, r=8, p=1, dklen=32) == expected)