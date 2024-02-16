from bs4 import BeautifulSoup
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import os
import subprocess
import shutil
import asyncio
import websockets


folder_source = "src"

path_main_css = "style.css"

folder_dist = "dist"

generated_html_file_name = "index.html"

# Liste globale pour stocker les chemins des fichiers sources
html_files_used = set()

connected = set()

# Create a new event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def replace_matrio_tags(path, original_content=None, matrio_class=None, isPage=False):
    if not os.path.exists(path):
        print(f"Path does not exist: {path}")
        return

    html_files_used.add(path)
    with open(path, "r") as f:
        contents = f.read()

    soup = BeautifulSoup(contents, "lxml")

    if matrio_class:
        # Find the div with the matrio-class attribute
        matrio_class_div = soup.find(attrs={"matrio-class": True})

        if matrio_class_div is not None:
            # Add the matrio class to the div
            matrio_class_div["class"] = matrio_class_div.get("class", []) + matrio_class
            del matrio_class_div["matrio-class"]

    # Replace <matrio-content> tags with the original content
    if original_content:
        # Remove all '\n' from the list
        original_content = [item for item in original_content if item != "\n"]

        # Convert the list to a string
        original_content_str = "".join(str(element) for element in original_content)

        # Check if the body exists
        if BeautifulSoup(original_content_str, "lxml").body is not None:
            for matrio_content_tag in soup.find_all("matrio-content"):
                matrio_content_tag.replace_with(
                    *BeautifulSoup(original_content_str, "lxml").body.contents,
                )
        else:
            for matrio_content_tag in soup.find_all("matrio-content"):
                matrio_content_tag.replace_with("")

    # Replace <matrio> tags with the content of the file they point to
    matrio_tags = soup.find_all("matrio")
    for tag in matrio_tags:
        if "path" in tag.attrs:
            child_path = folder_source + "/" + tag.attrs["path"] + ".html"
            if "class" in tag.attrs:
                matrio_class = tag.attrs["class"]
            child_contents = replace_matrio_tags(
                child_path,
                tag.contents,
                matrio_class if matrio_class else None,
            )
            if child_contents is not None:
                tag.replace_with(*BeautifulSoup(child_contents, "lxml").body.contents)
            else:
                print(f"Failed to replace matrio tag: {tag}")

    if isPage:
        # Create a new script tag
        script_tag = soup.new_tag("script")
        script_tag.attrs["src"] = "scripts/websockets.js"
        soup.body.append(script_tag)

    return str(soup)


def process_pages(source_folder, target_folder):
    for dirpath, dirnames, filenames in os.walk(source_folder):
        for filename in filenames:
            if filename.endswith(".html"):
                source_file_path = os.path.join(dirpath, filename)
                # Use the same folder structure in the dist folder as in the source folder
                # target_file_path = os.path.join(
                #     target_folder, os.path.relpath(source_file_path, source_folder)
                # )
                target_file_path = os.path.join(
                    target_folder, os.path.basename(source_file_path)
                )
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                html_content = replace_matrio_tags(source_file_path, None, None, True)
                with open(target_file_path, "w") as file:
                    file.write(html_content)


def create_combined_css_file():
    with open("dist/style.css", "w") as outfile:
        for source_file in html_files_used:
            css_file = source_file.rsplit(".", 1)[0] + ".css"
            if os.path.exists(css_file):
                outfile.write(f"/* Content from {css_file} */\n")
                with open(css_file, "r") as infile:
                    outfile.write(infile.read())
                    outfile.write("\n")


async def connect_and_send():
    print("Reloading the browser via WebSocket...")
    async with websockets.connect("ws://localhost:8765") as websocket:
        await websocket.send("reload")


class MyHandler(FileSystemEventHandler):
    def on_modified(self, event):
        print(f"Event type: {event.event_type}  path : {event.src_path}")
        if not event.is_directory and event.src_path.endswith((".html", ".css")):
            play()
            asyncio.run(connect_and_send())
        pass


def play():
    if not os.path.exists(folder_dist):
        os.makedirs(folder_dist)
    else:
        # Clean the dist folder
        shutil.rmtree(folder_dist)
        os.makedirs(folder_dist, exist_ok=True)

    # Copy assets to the dist folder
    shutil.copytree(
        os.path.join(folder_source, "assets"), os.path.join(folder_dist, "assets")
    )

    # Copy scripts to the dist folder
    shutil.copytree(
        os.path.join(folder_source, "scripts"), os.path.join(folder_dist, "scripts")
    )

    process_pages("src/pages", "dist")
    create_combined_css_file()


async def server(websocket, path):
    # Register.
    connected.add(websocket)
    try:
        async for message in websocket:
            # Handle received message
            await send_message_to_all_clients(message)
    finally:
        # Unregister.
        connected.remove(websocket)


async def send_message_to_all_clients(message):
    for ws in connected:
        if not ws.open:
            continue
        await ws.send(message)


def start_observer():
    # Set up the file observer
    event_handler = MyHandler()
    observer = Observer()
    observer.schedule(event_handler, path=folder_source, recursive=True)
    observer.start()

    # Keep the observer running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


async def start_websocket_server():
    start_server = websockets.serve(server, "localhost", 8765)
    await start_server
    await asyncio.Future()  #


if __name__ == "__main__":
    # Run the logic of matrio
    play()

    # Start the observer in a new thread
    observer_thread = threading.Thread(target=start_observer)
    observer_thread.start()

    try:
        # Start the WebSocket server as a new task
        websocket_server_task = loop.create_task(start_websocket_server())

        # Start the HTTP server
        print("Starting HTTP server...")
        httpd = subprocess.Popen(
            [
                "python",
                "-m",
                "http.server",
                "4200",
                "-d",
                folder_dist,
            ],
            stdout=subprocess.DEVNULL,  # Redirect stdout to DEVNULL
        )
        print(f"Serving HTTP on localhost port 4200 (http://localhost:4200/) ...")

        # Run the event loop
        loop.run_forever()
    except KeyboardInterrupt:
        # observer.stop()
        pass
    finally:
        print("Closing Loop")
        loop.close()


# Below is the code that I used to generate the dependency tree. I'm keeping it here for reference.

# def process_file(path, tree):
#     with open(path, "r") as f:
#         contents = f.read()

#     soup = BeautifulSoup(contents, "lxml")

#     matrio_tags = soup.find_all("matrio")
#     for tag in matrio_tags:
#         if "path" in tag.attrs:
#             chemin_fichier_cible = folder_source + "/" + tag.attrs["path"] + ".html"
#             if chemin_fichier_cible not in tree and not any(
#                 chemin_fichier_cible in v for v in tree.values()
#             ):
#                 if path not in tree:
#                     tree[path] = []
#                 tree[path].append(chemin_fichier_cible)
#                 process_file(chemin_fichier_cible, tree)
#     return tree

# def merge_css_files(original_css_path, dependency_tree, final_css_path):
#     # Create a set to store the paths of the CSS files that have been processed
#     processed_css_files = set()

#     # Open the final CSS file
#     with open(final_css_path, "w") as final_css_file:
#         # Open the original CSS file and write its contents to the final CSS file
#         with open(original_css_path, "r") as original_css_file:
#             final_css_file.write(f"/* CSS from {original_css_path} */\n")
#             final_css_file.write(original_css_file.read())
#         processed_css_files.add(original_css_path)

#         # Iterate over all files in the dependency tree
#         for path in list(dependency_tree.keys()) + [
#             item for sublist in list(dependency_tree.values()) for item in sublist
#         ]:
#             # Replace .html with .css in the path
#             css_path = path.rsplit(".", 1)[0] + ".css"
#             # If the CSS file exists and has not been processed yet, read its contents and write them to the final CSS file
#             if os.path.exists(css_path) and css_path not in processed_css_files:
#                 with open(css_path, "r") as css_file:
#                     final_css_file.write(f"\n/* CSS from {css_path} */\n")
#                     final_css_file.write(css_file.read())
#                 processed_css_files.add(css_path)


# def logic_when_there_is_only_one_page() {
#     # Parcourir tous les fichiers du dossier source et ses sous-dossiers
#     dependency_tree = {}
#     for dossier, sous_dossiers, fichiers in os.walk(folder_source):
#         for nom_fichier in fichiers:
#             if nom_fichier.endswith(".html"):
#                 chemin_fichier_source = os.path.join(dossier, nom_fichier)
#                 chemin_fichier_dist = os.path.join(folder_source, nom_fichier)
#                 if chemin_fichier_source not in dependency_tree and not any(
#                     chemin_fichier_source in v for v in dependency_tree.values()
#                 ):
#                     dependency_tree = process_file(
#                         chemin_fichier_source, dependency_tree
#                     )

#     # Find the root file (the file that is not a dependency of any other file)
#     root_file = next(
#         iter(
#             set(dependency_tree.keys())
#             - {item for sublist in dependency_tree.values() for item in sublist}
#         )
#     )
#     return root_file
# }
