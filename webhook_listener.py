#!/usr/bin/env python3
"""
Webhook Listener para deploy automático del Bot RSI
Escucha webhooks de GitHub y ejecuta deploy.sh automáticamente
"""

import http.server
import socketserver
import subprocess
import json
import hmac
import hashlib
import os
import logging
from datetime import datetime

PORT = 9000
SECRET = os.getenv('WEBHOOK_SECRET', 'default_secret_change_me')
DEPLOY_SCRIPT = './deploy.sh'

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('webhook.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class WebhookHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override para usar nuestro logger"""
        logger.info(format % args)
    
    def do_GET(self):
        """Responder a peticiones GET con status"""
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            status = {
                'status': 'online',
                'timestamp': datetime.now().isoformat(),
                'webhook_endpoint': '/webhook',
                'last_deploy': self.get_last_deploy()
            }
            
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'404 Not Found\nUse /webhook for GitHub webhooks or /status for status')
    
    def do_POST(self):
        """Manejar webhooks de GitHub"""
        if self.path != '/webhook':
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'404 Not Found')
            return
        
        try:
            # Leer datos del POST
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error_response(400, "No content")
                return
            
            post_data = self.rfile.read(content_length)
            
            # Verificar signature de GitHub (opcional pero recomendado)
            github_signature = self.headers.get('X-Hub-Signature-256')
            if github_signature and SECRET != 'default_secret_change_me':
                if not self.verify_signature(post_data, github_signature):
                    logger.warning(f"Invalid signature from {self.client_address[0]}")
                    self.send_error_response(401, "Invalid signature")
                    return
            
            # Parsear JSON
            try:
                payload = json.loads(post_data.decode('utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                self.send_error_response(400, "Invalid JSON")
                return
            
            # Verificar que sea un push al branch main
            if not self.is_valid_push(payload):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Webhook received but not a push to main branch')
                return
            
            # Log información del push
            repo_name = payload.get('repository', {}).get('name', 'unknown')
            pusher = payload.get('pusher', {}).get('name', 'unknown')
            commits = payload.get('commits', [])
            
            logger.info(f"Push received from {pusher} to {repo_name}")
            logger.info(f"Commits: {len(commits)}")
            
            # Ejecutar deploy
            success, output = self.execute_deploy()
            
            if success:
                response_text = f"Deploy successful!\n\nOutput:\n{output}"
                logger.info("Deploy completed successfully")
            else:
                response_text = f"Deploy failed!\n\nError:\n{output}"
                logger.error("Deploy failed")
            
            # Responder a GitHub
            self.send_response(200 if success else 500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(response_text.encode())
            
            # Log en archivo separado para deploys
            self.log_deploy(success, pusher, commits, output)
            
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            self.send_error_response(500, f"Internal error: {str(e)}")
    
    def verify_signature(self, payload, signature):
        """Verificar signature de GitHub"""
        expected = 'sha256=' + hmac.new(
            SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    def is_valid_push(self, payload):
        """Verificar que sea un push válido al branch main"""
        if payload.get('ref') != 'refs/heads/main':
            logger