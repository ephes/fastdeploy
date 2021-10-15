import json
import asyncio


async def run_deploy(connection_manager):
    print("running deployment")
    proc = await asyncio.create_subprocess_shell(
        "deployments/cast_hosting.sh",
        # "deployments/sample.sh",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    while True:
        data = await proc.stdout.readline()
        if len(data) == 0:
            break

        decoded = data.decode("UTF-8")
        try:
            data = json.loads(decoded)
            print("data: ", data)
            await connection_manager.broadcast(data)
        except json.decoder.JSONDecodeError:
            print("could not json decode: ", decoded)
            pass

    print("return code:", proc.returncode)
    print("deployment complete")
