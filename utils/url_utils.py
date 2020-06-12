def get_ssh_url_from_list(url_list):
    for url_dict in url_list:
        if "name" in url_dict and url_dict["name"] == "ssh":
            return url_dict["href"]

    return None
