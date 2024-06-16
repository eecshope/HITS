import argparse
import json

from utils.config import *


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--put_root", required=True, help="Root dir of PUTs in this PC. E.g. 'root/put'")
    args = parser.parse_args()
    project_name = args.project_name
    put_root = args.put_root

    # Step 4: export everything to MongoDB
    # trial on mongo
    from pymongo import MongoClient

    client = MongoClient(mongo_url, port=mongo_port)
    db = client[project_name]  # MongoDB doesn’t create a database until you have collections and documents in it.

    # Create local working dir and write local meta info
    playground_root = os.path.join(playground_dir, project_name).__str__()
    put_path = os.path.join(put_root, project_name)
    mut_names = list(db.list_collection_names())
    method_name_to_idx = dict({})
    idx_to_method_name = dict({})
    for idx, mut_name in enumerate(mut_names):
        method_name_to_idx[mut_name] = f"method_{idx}"
        idx_to_method_name[f"method_{idx}"] = mut_name
    os.makedirs(playground_root, exist_ok=True)
    with open(os.path.join(playground_root, "meta.json"), 'w') as file:
        json.dump({"project_name": project_name, "put_path": os.path.abspath(put_path), "method_name_to_idx": method_name_to_idx,
                   "idx_to_method_name": idx_to_method_name}, file)
    for idx in idx_to_method_name:
        os.makedirs(os.path.join(playground_root, 'methods', idx), exist_ok=True)


if __name__ == "__main__":
    main()
