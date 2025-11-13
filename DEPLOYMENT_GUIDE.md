# Transcript Analysis Application - Deployment Guide

## ✅ Quick Start (Now Only ONE Command!)

Instead of running two commands, you now only need:

```bash
python3 flask_backend.py
```

That's it! Flask now serves both the API and the frontend.

### Access the Application:
- **Local**: http://localhost:5000
- **Network**: http://<your-ip>:5000 (shown in terminal when you start the server)

The server will display all access URLs when it starts.

---

## 🌐 Deployment Options

### Option 1: Local Network Access (Easiest)

**Best for**: Sharing with colleagues on the same office network

**Steps**:
1. Run `python3 flask_backend.py`
2. Note the "Network" URL displayed (e.g., http://192.168.1.100:5000)
3. Share that URL with colleagues on your network
4. Make sure port 5000 is open in your firewall:
   ```bash
   # Ubuntu/Debian
   sudo ufw allow 5000

   # Windows
   # Go to Windows Firewall → Advanced Settings → Inbound Rules → New Rule → Port 5000
   ```

**Limitations**:
- Only accessible on your local network
- Server must keep running on your machine
- If your computer sleeps/shuts down, the app goes down

---

### Option 2: Production Deployment with Gunicorn (Recommended for Servers)

**Best for**: Running on a dedicated server (Linux VM, cloud instance, etc.)

**Steps**:

1. **Install Gunicorn**:
   ```bash
   pip install gunicorn
   ```

2. **Create a startup script** (`start_server.sh`):
   ```bash
   #!/bin/bash
   cd /home/user/TranscriptsToChat
   gunicorn -w 4 -b 0.0.0.0:5000 flask_backend:app --timeout 300
   ```

3. **Make it executable**:
   ```bash
   chmod +x start_server.sh
   ```

4. **Run it**:
   ```bash
   ./start_server.sh
   ```

5. **Keep it running 24/7 with systemd** (Linux):

   Create `/etc/systemd/system/transcript-analysis.service`:
   ```ini
   [Unit]
   Description=Transcript Analysis Application
   After=network.target

   [Service]
   Type=simple
   User=youruser
   WorkingDirectory=/home/user/TranscriptsToChat
   ExecStart=/usr/bin/gunicorn -w 4 -b 0.0.0.0:5000 flask_backend:app --timeout 300
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   Then:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable transcript-analysis
   sudo systemctl start transcript-analysis
   sudo systemctl status transcript-analysis  # Check if running
   ```

**Benefits**:
- Runs 24/7, even if you log out
- Handles multiple users better
- Auto-restarts if it crashes

---

### Option 3: Cloud Deployment

**Best for**: Remote access from anywhere, internet-accessible

#### A. AWS EC2 (Amazon Web Services)

1. **Launch EC2 instance** (Ubuntu 22.04 recommended)
2. **Configure Security Group** - Allow port 5000
3. **Install dependencies**:
   ```bash
   sudo apt update
   sudo apt install python3-pip
   pip3 install flask flask-cors pandas
   ```
4. **Upload your code** (using scp or git clone)
5. **Run with Gunicorn** (see Option 2)
6. **Access via**: http://<ec2-public-ip>:5000

**Cost**: ~$5-30/month depending on instance size

#### B. DigitalOcean Droplet

1. **Create Droplet** (Ubuntu, $6/month minimum)
2. **Same steps as EC2**
3. **Access via**: http://<droplet-ip>:5000

#### C. Heroku (Easiest Cloud Option)

1. **Create `Procfile`**:
   ```
   web: gunicorn flask_backend:app
   ```

2. **Create `requirements.txt`**:
   ```bash
   pip freeze > requirements.txt
   ```

3. **Deploy**:
   ```bash
   heroku login
   heroku create your-app-name
   git push heroku main
   ```

**Cost**: Free tier available, $7/month for basic

---

### Option 4: Docker Container (For Advanced Users)

**Best for**: Consistent deployment across different environments

1. **Create `Dockerfile`**:
   ```dockerfile
   FROM python:3.9-slim

   WORKDIR /app
   COPY . .

   RUN pip install --no-cache-dir flask flask-cors pandas gunicorn

   EXPOSE 5000

   CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "flask_backend:app", "--timeout", "300"]
   ```

2. **Build and run**:
   ```bash
   docker build -t transcript-analysis .
   docker run -p 5000:5000 -v $(pwd)/data:/app/data transcript-analysis
   ```

---

## 🔒 Security Considerations

### For Production Deployment:

1. **Add Authentication** - Currently anyone with the URL can access it
   - Consider adding basic auth or OAuth
   - Use nginx as reverse proxy with SSL

2. **Use HTTPS** - Get a free SSL certificate from Let's Encrypt:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx
   ```

3. **Environment Variables** - Don't hardcode sensitive data:
   ```python
   import os
   DB_PATH = os.getenv('DB_PATH', 'data/transcript_projects.db')
   ```

4. **Firewall** - Only allow necessary ports:
   ```bash
   sudo ufw allow ssh
   sudo ufw allow 5000
   sudo ufw enable
   ```

5. **Regular Backups** - Backup your data folder:
   ```bash
   tar -czf backup-$(date +%Y%m%d).tar.gz data/
   ```

---

## 🗄️ Database Location

**Important Change**: The database is now stored in `data/transcript_projects.db` instead of `/tmp/`.

**Why**: `/tmp/` gets cleared on reboot, losing all your data!

**To backup**:
```bash
cp data/transcript_projects.db data/transcript_projects.db.backup
```

---

## 📊 Monitoring & Logs

### View logs in real-time:
```bash
# If running with systemd
sudo journalctl -u transcript-analysis -f

# If running manually
python3 flask_backend.py 2>&1 | tee app.log
```

### Check if server is running:
```bash
curl http://localhost:5000/api/health
```

Should return: `{"status":"healthy"}`

---

## 🆘 Troubleshooting

### "Address already in use" error:
```bash
# Find what's using port 5000
sudo lsof -i :5000

# Kill the process
sudo kill -9 <PID>
```

### Can't access from other computers:
1. Check firewall: `sudo ufw status`
2. Verify server is listening on 0.0.0.0: `netstat -an | grep 5000`
3. Check router/network firewall settings

### Slow performance with many users:
- Increase Gunicorn workers: `-w 8` (2x CPU cores recommended)
- Add Redis for caching
- Use nginx as reverse proxy

---

## 📞 Quick Reference

| Need | Command |
|------|---------|
| Start server | `python3 flask_backend.py` |
| Production server | `gunicorn -w 4 -b 0.0.0.0:5000 flask_backend:app --timeout 300` |
| Check health | `curl http://localhost:5000/api/health` |
| View logs | `sudo journalctl -u transcript-analysis -f` |
| Restart service | `sudo systemctl restart transcript-analysis` |
| Backup data | `tar -czf backup.tar.gz data/` |

---

## 🎯 Recommended Setup

**For 1-10 users on local network**:
- Run directly with Python: `python3 flask_backend.py`
- Share the Network URL

**For 10-100 users on dedicated server**:
- Use Gunicorn with systemd
- Add nginx reverse proxy
- Enable HTTPS with Let's Encrypt

**For internet access**:
- Deploy to AWS/DigitalOcean
- Use Gunicorn + nginx + SSL
- Consider adding authentication

---

## 📝 What Changed from Your Original Setup

| Before | After |
|--------|-------|
| Two commands (http.server + flask) | One command (flask only) |
| API at localhost:5000 | Everything at one URL |
| Database in `/tmp/` (temporary) | Database in `data/` (persistent) |
| Hardcoded localhost | Dynamic URL (works remotely) |
| Only local access | Network/internet ready |

---

Need help? Check the Flask documentation or ask for assistance!
