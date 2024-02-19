apt-get update
echo "Installing ssh client (for node-red github integration)..."
apt-get -y install openssh-client
echo "Installed ssh client (for node-red github integration)."

echo "Installing canvas (for roomba)..."
apt-get -y install build-essential libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev
sudo npm install canvas --unsafe-perm=true
echo "Installed canvas (for roomba)."

echo "Configuring git for GitHub user ${GITHUB_USER} with E-Mail ${GITHUB_EMAIL}"
git config --global user.name "${GITHUB_USER}"
git config --global user.email "${GITHUB_EMAIL}"
