# Cloud Upload

Just starting the project so stay tuned...

## What I Am Building

A photographer traveling carries a lot of equipment and uses high speed SD cards for the camera image and video storing. These cards are expensive, so there is never enough of them. Additionally the images saved need to be securely storred and backed up. I am building an ESP32 based device accessible via WiFi from a web browser for full configuration and control. Functionallity:
- reading an SD card you can plug-in and un-plug at will
- backing up the data to an internal SD card used as a buffer
- uploading the data to a dedicated web service "Cloud Upload" at cloudupload.ujagaga.in.rs
- uploading and downloading files via WiFi file server
- the web service to which this device uploads uses GDrive API to upload data to GDrive

