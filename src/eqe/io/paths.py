import os
import datetime


def create_user_directory(data_dir, user, debug=False):
    """
    Create and return the dated user directory for measurement data.

    Example:
        C:\\Users\\...\\Data\\user\\260310_IPCE
    """
    user_dir = os.path.join(data_dir, user)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    format_dt = "%Y-%m-%d %H:%M:%S.%f"
    datetime_object = datetime.datetime.strptime(str(datetime.datetime.now()), format_dt)
    date = datetime_object.strftime("%y%m%d") + "_IPCE"

    user_dir = os.path.join(data_dir, user, date)

    if debug:
        print(date)
        print(user_dir)

    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    return user_dir