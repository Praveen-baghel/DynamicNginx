from flask import Flask, request, jsonify
import subprocess
import os
import shutil

app = Flask(__name__)

DYNAMIC_CONF_PATH = "/etc/nginx/sites-available/dynamic_nginx.conf"
BACKUP_CONF_PATH = "/etc/nginx/sites-available/dynamic_nginx_backup.conf"


@app.route('/add-domain', methods=['POST'])
def add_domain():
    data = request.json
    domain = data.get("domain")
    ip = data.get("ip")
    access_token = request.headers.get("access-token")
    if access_token != "your_access_token":  # use any auth method you want
        return jsonify({"status": "unauthorised"}), 400

    if not domain or not ip:
        return jsonify({"error": "Missing domain or IP"}), 400

    config_snippet = f"""server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://{ip};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

    try:
        with open(DYNAMIC_CONF_PATH, 'r') as file:
            config_content = file.read()

        # Check if the configuration for this domain and IP already exists
        if f"server_name {domain};" in config_content and f"proxy_pass http://{ip};" in config_content:
            return jsonify({"status": "success", "message": "Configuration already exists"}), 200

        # Create a backup of the original configuration
        shutil.copy(DYNAMIC_CONF_PATH, BACKUP_CONF_PATH)

        # Append the new configuration to the dynamic.conf file
        with open(DYNAMIC_CONF_PATH, 'a') as file:
            file.write(config_snippet)

        # Test the new configuration for syntax errors
        test_result = subprocess.run(
            ["sudo", "nginx", "-t"], capture_output=True, text=True)

        if test_result.returncode != 0:
            # If there is a syntax error, revert the changes
            shutil.copy(BACKUP_CONF_PATH, DYNAMIC_CONF_PATH)
            return jsonify({"error": "Configuration test failed", "details": test_result.stderr}), 500

        # Reload Nginx to apply the changes
        subprocess.run(["sudo", "nginx", "-s", "reload"], check=True)

        return jsonify({"status": "success", "message": "Configuration added"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # Clean up the backup file if it exists
        if os.path.exists(BACKUP_CONF_PATH):
            os.remove(BACKUP_CONF_PATH)


@app.route('/remove-domain', methods=['POST'])
def remove_domain():
    data = request.json
    domain = data.get("domain")
    ip = data.get("ip")
    access_token = request.headers.get("access-token")
    if access_token != "salazar@captains":
        return jsonify({"status": "failure", "message": "Unauthorised"}), 400

    if not domain or not ip:
        return jsonify({"error": "Missing domain or IP"}), 400

    try:
        # Create a backup of the original configuration
        shutil.copy(DYNAMIC_CONF_PATH, BACKUP_CONF_PATH)

        # Read the current configuration
        with open(DYNAMIC_CONF_PATH, 'r') as file:
            lines = file.readlines()

        start_index = -1
        end_index = -1
        location_block_end = False
        # Find the start and end of the server block that matches the domain and IP
        for i, line in enumerate(lines):
            if start_index != -1 and location_block_end and line.strip() == "}":
                if domain_found and ip_found:
                    end_index = i
                    break
                else:
                    start_index = -1
                    domain_found = False
                    ip_found = False

            if line.strip().startswith("server {"):
                start_index = i

            if start_index != -1 and "server_name" in line and domain in line:
                domain_found = True

            if start_index != -1 and "proxy_pass" in line and ip in line:
                ip_found = True

            if start_index != -1 and line.strip() == "}":
                location_block_end = True

        if start_index != -1 and end_index != -1:
            # Remove the block by slicing out the lines
            new_lines = lines[:start_index] + lines[end_index + 1:]

            # Write the new configuration back to the file
            with open(DYNAMIC_CONF_PATH, 'w') as file:
                file.writelines(new_lines)

            # Test the new configuration for syntax errors
            test_result = subprocess.run(
                ["sudo", "nginx", "-t"], capture_output=True, text=True)
            if test_result.returncode != 0:
                # If there is a syntax error, revert the changes
                shutil.copy(BACKUP_CONF_PATH, DYNAMIC_CONF_PATH)
                return jsonify({"error": "Configuration test failed", "details": test_result.stderr}), 500

            # Reload Nginx to apply the changes
            subprocess.run(["sudo", "nginx", "-s", "reload"], check=True)

            return jsonify({"status": "success", "message": "Configuration removed"}), 200
        else:
            return jsonify({"error": "Block not found"}), 404

    except Exception as e:
        # On any exception, revert the configuration
        shutil.copy(BACKUP_CONF_PATH, DYNAMIC_CONF_PATH)
        return jsonify({"error": str(e)}), 500

    finally:
        # Clean up the backup file if it exists
        if os.path.exists(BACKUP_CONF_PATH):
            os.remove(BACKUP_CONF_PATH)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
