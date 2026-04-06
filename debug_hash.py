import security

p = "admin123"
print(f"Hashing '{p}' (length {len(p)})")
h = security.hash_password(p)
print(f"Hashed: {h}")

print(f"Verifying {p} against {h}")
v = security.verify_password(p, h)
print(f"Verified: {v}")
