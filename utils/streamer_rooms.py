def split_streamer_rooms(uids, user_infos):
    """Keep UID/room pairs aligned and name accounts without a usable room."""
    valid_uids, room_ids, without_rooms = [], [], []
    for uid in uids:
        user = user_infos.get(str(uid))
        if user is None:
            continue
        room_id = user.get("room_id")
        if type(room_id) is not int or room_id <= 0:
            without_rooms.append(user.get("name") or str(uid))
            continue
        valid_uids.append(uid)
        room_ids.append(room_id)
    return valid_uids, room_ids, without_rooms
