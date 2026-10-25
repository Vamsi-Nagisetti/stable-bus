
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Create a folder for development keys
secrets_dir = Path("secrets")
secrets_dir.mkdir(exist_ok=True)

# Generate a 2048-bit RSA private key
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Export private key in PEM format
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

# Export the corresponding public key
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

# Save keys locally
(secrets_dir / "jwt_private.pem").write_bytes(private_pem)
(secrets_dir / "jwt_public.pem").write_bytes(public_pem)

print("JWT development key pair generated successfully.")
