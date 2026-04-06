apt-get update
echo "Installing ssh client (for node-red github integration)..."
apt-get -y install openssh-client
echo "Installed ssh client (for node-red github integration)."

echo "Configuring git for GitHub user ${GITHUB_USER} with E-Mail ${GITHUB_EMAIL}"
git config --global user.name "${GITHUB_USER}"
git config --global user.email "${GITHUB_EMAIL}"
