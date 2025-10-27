from fastapi import FastAPI , Request
from proxmoxer import ProxmoxAPI
import subprocess, time, pymysql
import subprocess
import os
from dotenv import load_dotenv

app = FastAPI()

load_dotenv()


PROXMOX_HOST = os.getenv("PROXMOX_HOST")
PROXMOX_USER = os.getenv("PROXMOX_USER")
PROXMOX_TOKEN_NAME = os.getenv("PROXMOX_TOKEN_NAME")
PROXMOX_TOKEN_VALUE = os.getenv("PROXMOX_TOKEN_VALUE")
NODE = os.getenv("NODE")
TEMPLATE_ID = os.getenv("TEMPLATE_ID")
TTL = 3600

MYSQL_HOSTNAME= os.getenv("MYSQL_HOSTNAME")
MYSQL_DATABASE= os.getenv("MYSQL_DATABASE")
MYSQL_USERNAME= os.getenv("MYSQL_USERNAME")
MYSQL_PASSWORD= os.getenv("MYSQL_PASSWORD")

lxc_user = os.getenv("lxc_user")
container_passwd = os.getenv("container_passwd")

proxmox=ProxmoxAPI(
    PROXMOX_HOST,
    user=PROXMOX_USER,
    token_name=PROXMOX_TOKEN_NAME,
    token_value=PROXMOX_TOKEN_VALUE,
    verify_ssl=False
)


@app.post("/launch")
async def launch(request: Request):
    data = await request.json()
    netid = data.get("netid", "").strip()
    cid = proxmox.cluster.nextid.get()
    print(f"Next available LXC ID: {cid}")

    try:
        proxmox.nodes(NODE).lxc(TEMPLATE_ID).clone.post(
            newid=cid,
            hostname=f"{netid}-{cid}",
            full=1,
         )

        time.sleep(10)
        proxmox.nodes(NODE).lxc(cid).status.start.post()

        time.sleep(10)

        status = proxmox.nodes(NODE).lxc(cid).interfaces.get()

        print("status is \n" , status)

        ip_info = status[1]["inet"]

        print("ip_info is \n" , ip_info)

        ip = ip_info.split('/')[0]

        print("ip is \n" , ip)

        conn = pymysql.connect(
        host=MYSQL_HOSTNAME,
        user=MYSQL_USERNAME,
        password = MYSQL_PASSWORD,
        db=MYSQL_DATABASE,
        port = 3306
        )

        cur = conn.cursor()

        cur.execute("INSERT INTO guacamole_connection (connection_name, protocol) VALUES (%s, 'ssh')", (f"{netid}-{cid}",))

        conn_id = cur.lastrowid

        cur.executemany(
            "INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value) VALUES (%s,%s,%s)",
            [(conn_id,'hostname',ip),(conn_id,'port','22'),(conn_id,'username',lxc_user),(conn_id,'password',container_passwd)]
        )

        cur.execute("INSERT INTO guacamole_entity (name, type) VALUES (%s, 'USER')", (netid,))

        entity_id = cur.lastrowid

        cur.execute("INSERT INTO guacamole_connection_permission (entity_id, connection_id , permission) VALUES (%s, %s , 'READ')", (entity_id , netid ,))

        conn.commit(); conn.close()

        return {
            "success": True,
            "container_id": cid,
            "ip": ip,
            "user": netid,
            "password": container_passwd,
            "url": f"http://{MYSQL_HOSTNAME}:8080/guacamole/#/client/{conn_id}",
            "expires_in": TTL
        }

    except Exception as e:
        return {"success": False, "message": str(e)}