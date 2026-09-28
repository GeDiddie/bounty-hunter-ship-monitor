# Ship Monitor on lookout222

On the Jetson terminal:

```bash
cd ~
curl -L -o sm.zip https://github.com/GeDiddie/bounty-hunter-ship-monitor/archive/refs/heads/main.zip
unzip sm.zip
mv bounty-hunter-ship-monitor-main ship-monitor
cd ship-monitor
python3 server.py
```

Leave that window open. On the tablet, Bounty Hunter Wi-Fi:

http://192.168.50.14:8088/
