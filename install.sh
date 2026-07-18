#!/usr/bin/env bash

SERVICE_NAME=image_upload_server.service
SERVICE_FILE=/etc/systemd/system/$SERVICE_NAME

# --- Installation Section ---
echo "Installing dependencies..."
if ! sudo apt update -y; then
  echo "Error: Failed to update apt repositories. Aborting installation."
  exit 1
fi

if ! sudo apt install -y python3-pip python3-venv; then
  echo "Error: Failed to install dependencies. Aborting installation."
  exit 1
fi

echo "Creating virtual environment..."
python3 -m venv .venv
if [ $? -ne 0 ]; then
  echo "Error: Failed to create virtual environment. Aborting installation."
  exit 1
fi

echo "Activating virtual environment..."
source .venv/bin/activate
if [ $? -ne 0 ]; then
  echo "Error: Failed to activate virtual environment. Aborting installation."
  exit 1
fi

echo "Installing Python packages..."
pip3 install flask flask-wtf google-api-python-client google-auth google-auth-oauthlib gunicorn requests
if [ $? -ne 0 ]; then
  echo "Error: Failed to install python libraries. Aborting installation."
  exit 1
fi

echo "Deactivating virtual environment..."
deactivate

echo "Making run_server.sh executable..."
chmod +x run_server.sh
if [ $? -ne 0 ]; then
  echo "Error: Failed to make run_server.sh executable. Aborting installation."
  exit 1
fi

# --- SD Card Automount Setup ---
echo "Installing SD card automount script..."
sudo cp helpers/sd-automount.sh /usr/local/bin/sd-automount.sh
sudo chmod +x /usr/local/bin/sd-automount.sh
if [ $? -ne 0 ]; then
  echo "Error: Failed to install sd-automount.sh. Aborting installation."
  exit 1
fi

echo "Writing SD automount config for user $USER..."
echo "MOUNT_USER=$USER" | sudo tee /etc/sd-automount.conf > /dev/null
if [ $? -ne 0 ]; then
  echo "Error: Failed to write /etc/sd-automount.conf. Aborting installation."
  exit 1
fi

echo "Installing SD card automount udev rule..."
sudo cp helpers/99-sdcard-automount.rules /etc/udev/rules.d/99-sdcard-automount.rules
if [ $? -ne 0 ]; then
  echo "Error: Failed to install udev rule. Aborting installation."
  exit 1
fi

echo "Reloading udev rules..."
sudo udevadm control --reload-rules
sudo udevadm trigger
if [ $? -ne 0 ]; then
  echo "Error: Failed to reload udev rules. Aborting installation."
  exit 1
fi

# --- Service File Creation ---
echo "Creating systemd service file: $SERVICE_FILE"
cat <<EOF > "$PWD/$SERVICE_NAME"
[Unit]
Description=Image Upload Server
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=$PWD/run_server.sh
WorkingDirectory=$PWD
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
if [ $? -ne 0 ]; then
  echo "Error: Failed to create the service file. Aborting installation."
  exit 1
fi
sudo mv "$PWD/$SERVICE_NAME" "$SERVICE_FILE"
if [ $? -ne 0 ]; then
  echo "Error: Failed to move the service file to $SERVICE_FILE. Aborting installation."
  exit 1
fi

# --- Service Management ---
echo "Reloading systemd unit files..."
sudo systemctl daemon-reload
if [ $? -ne 0 ]; then
  echo "Error: Failed to reload systemd units. Installation incomplete."
  exit 1
fi

echo "Enabling and restarting the service..."
sudo systemctl enable "$SERVICE_NAME"
if [ $? -ne 0 ]; then
  echo "Error: Failed to enable the service. Installation incomplete."
  exit 1
fi
sudo systemctl restart "$SERVICE_NAME"
if [ $? -ne 0 ]; then
  echo "Error: Failed to start the service. Installation incomplete."
  exit 1
fi

echo "Image Upload Server installation and service started successfully!"

exit 0