#!/bin/bash

# Script to initialize .env from .env.sample with random passwords

if [ -f .env ]; then
    echo "[!] .env file already exists. Do you want to overwrite it? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "[*] Aborted. No changes made."
        exit 0
    fi
fi

# Function to generate a random alphanumeric string
generate_password() {
    local length=$1
    # Use openssl if available, otherwise fallback to /dev/urandom
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c "$length"
    else
        tr -dc 'a-zA-Z0-9' </dev/urandom | head -c "$length"
    fi
}

RANDOM_SECRET=$(generate_password 48)
RANDOM_ADMIN_PASS=$(generate_password 16)

# Copy sample to env
cp .env.sample .env

# Replace placeholders
# Use a different delimiter for sed in case of special characters (though we filtered for alphanumeric)
sed -i "s/GENERATE_RANDOM_SECRET/$RANDOM_SECRET/g" .env
sed -i "s/GENERATE_RANDOM_PASSWORD/$RANDOM_ADMIN_PASS/g" .env

echo "[+] Created .env from .env.sample"
echo "[+] Generated random SECRET_KEY: $RANDOM_SECRET"
echo "[+] Generated random ADMIN_PASS: $RANDOM_ADMIN_PASS"
echo "[*] IMPORTANT: Save your admin password! Default user: admin"
echo "[*] You can now edit .env to customize other settings."
