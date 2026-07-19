#!/usr/bin/env bash

SERVICE_NAME=image_upload_server.service
SERVICE_FILE=/etc/systemd/system/$SERVICE_NAME

# --- Installation Section ---
echo "Installing dependencies..."
if ! sudo apt update -y; then
  echo "Error: Failed to update apt repositories. Aborting installation."
  exit 1
fi

if ! sudo apt install -y python3-pip python3-venv hostapd dnsmasq; then
  echo "Error: Failed to install dependencies. Aborting installation."
  exit 1
fi

# The Debian/Ubuntu hostapd and dnsmasq packages auto-start a stock instance
# on install, listening with default (or no) config. This app runs its own
# instances of both, scoped to wlan0 only, so mask the stock ones to avoid
# two copies fighting over the interface.
sudo systemctl disable --now hostapd.service dnsmasq.service 2>/dev/null
sudo systemctl mask hostapd.service dnsmasq.service

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
pip3 install flask flask-wtf google-api-python-client google-auth google-auth-oauthlib gunicorn requests luma.oled
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

echo "Allowing $USER to run the automount helper as root (for the manual Mount button)..."
echo "$USER ALL=(root) NOPASSWD: /usr/local/bin/sd-automount.sh" | sudo tee "$PWD/sd-automount-sudoers" > /dev/null
sudo visudo -cf "$PWD/sd-automount-sudoers"
if [ $? -ne 0 ]; then
  echo "Error: Generated sudoers rule failed validation. Aborting installation."
  rm -f "$PWD/sd-automount-sudoers"
  exit 1
fi
sudo mv "$PWD/sd-automount-sudoers" /etc/sudoers.d/sd-automount
sudo chmod 440 /etc/sudoers.d/sd-automount

# --- WiFi Setup (fallback AP when there's no internet) ---
echo "Installing WiFi setup scripts..."
sudo cp helpers/wifi-ap.sh /usr/local/bin/wifi-ap.sh
sudo cp helpers/wifi-sta.sh /usr/local/bin/wifi-sta.sh
sudo cp helpers/wifi-scan.sh /usr/local/bin/wifi-scan.sh
sudo chmod +x /usr/local/bin/wifi-ap.sh /usr/local/bin/wifi-sta.sh /usr/local/bin/wifi-scan.sh
if [ $? -ne 0 ]; then
  echo "Error: Failed to install WiFi setup scripts. Aborting installation."
  exit 1
fi

echo "Allowing $USER to run the WiFi setup scripts as root..."
cat <<EOF | sudo tee "$PWD/wifi-sudoers" > /dev/null
$USER ALL=(root) NOPASSWD: /usr/local/bin/wifi-ap.sh
$USER ALL=(root) NOPASSWD: /usr/local/bin/wifi-sta.sh
$USER ALL=(root) NOPASSWD: /usr/local/bin/wifi-scan.sh
$USER ALL=(root) NOPASSWD: /usr/bin/resolvectl mdns wlan0 yes
EOF
sudo visudo -cf "$PWD/wifi-sudoers"
if [ $? -ne 0 ]; then
  echo "Error: Generated WiFi sudoers rule failed validation. Aborting installation."
  rm -f "$PWD/wifi-sudoers"
  exit 1
fi
sudo mv "$PWD/wifi-sudoers" /etc/sudoers.d/cloud-upload-wifi
sudo chmod 440 /etc/sudoers.d/cloud-upload-wifi

echo "Enabling mDNS globally (needed for the per-link mDNS resolvectl sets after connecting)..."
if ! grep -q "^MulticastDNS=yes" /etc/systemd/resolved.conf 2>/dev/null; then
  sudo sed -i 's/^#\?MulticastDNS=.*/MulticastDNS=yes/' /etc/systemd/resolved.conf
  grep -q "^MulticastDNS=yes" /etc/systemd/resolved.conf || echo "MulticastDNS=yes" | sudo tee -a /etc/systemd/resolved.conf > /dev/null
  sudo systemctl restart systemd-resolved
fi

# wlan0 is now controlled directly (wifi-ap.sh / wifi-sta.sh), not through
# Netplan — remove any leftover Netplan wifi config from an earlier install
# and disable the system wpa_supplicant service Netplan used to drive, since
# this app runs its own dedicated wpa_supplicant instance instead. Ethernet
# stays fully managed by Netplan; its config never mentions wlan0.
echo "Removing Netplan-based WiFi config (now handled directly)..."
sudo rm -f /etc/netplan/90-cloud-upload-wifi.yaml
sudo systemctl disable --now wpa_supplicant.service 2>/dev/null
sudo systemctl mask wpa_supplicant.service

# --- I2C OLED status display (optional hardware; harmless if not wired) ---
echo "Adding $USER to the i2c group (for /dev/i2c-* access, e.g. the status display)..."
sudo usermod -aG i2c "$USER"

# --- Flash persistence (token.json, known_networks.json survive a reboot
# in RAM-only mode) ---
echo "Installing flash-persist script..."
sudo cp helpers/flash-persist.sh /usr/local/bin/flash-persist.sh
sudo chmod +x /usr/local/bin/flash-persist.sh
if [ $? -ne 0 ]; then
  echo "Error: Failed to install flash-persist.sh. Aborting installation."
  exit 1
fi

echo "Allowing $USER to run flash-persist.sh as root..."
echo "$USER ALL=(root) NOPASSWD: /usr/local/bin/flash-persist.sh" | sudo tee "$PWD/flash-persist-sudoers" > /dev/null
sudo visudo -cf "$PWD/flash-persist-sudoers"
if [ $? -ne 0 ]; then
  echo "Error: Generated flash-persist sudoers rule failed validation. Aborting installation."
  rm -f "$PWD/flash-persist-sudoers"
  exit 1
fi
sudo mv "$PWD/flash-persist-sudoers" /etc/sudoers.d/flash-persist
sudo chmod 440 /etc/sudoers.d/flash-persist

# --- Shutdown button ---
echo "Allowing $USER to power off the device (for the home page shutdown button)..."
echo "$USER ALL=(root) NOPASSWD: /usr/sbin/poweroff" | sudo tee "$PWD/shutdown-sudoers" > /dev/null
sudo visudo -cf "$PWD/shutdown-sudoers"
if [ $? -ne 0 ]; then
  echo "Error: Generated shutdown sudoers rule failed validation. Aborting installation."
  rm -f "$PWD/shutdown-sudoers"
  exit 1
fi
sudo mv "$PWD/shutdown-sudoers" /etc/sudoers.d/shutdown
sudo chmod 440 /etc/sudoers.d/shutdown

# --- Service File Creation ---
echo "Creating systemd service file: $SERVICE_FILE"
cat <<EOF > "$PWD/$SERVICE_NAME"
[Unit]
Description=Image Uploader
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

echo "Image Uploader installation and service started successfully!"

exit 0