import os
import logging
import socket
import subprocess

logger = logging.getLogger(__name__)

def makedirs_if_not_exists(dir_name):
    try:
        os.makedirs(dir_name)
    except OSError as e:
        if not os.path.isdir(dir_name):
            raise e


def date2dir(d):
    """
    from isodate to yyyymmdd (format for directory name)
    Args:
        d (String): iso date string

    Returns:
        String: yyyymmdd
    """
    return "".join(d.split("-"))[:8]


def get_normalized_hostname(domain):
    hostname = socket.gethostname()
    if domain not in hostname:
        hostname = hostname + "." + domain
    return hostname


def copy_images_to_local(images_list, settings):
    stack_dir = settings.data_dir
    makedirs_if_not_exists(stack_dir)
    local_hostname = get_normalized_hostname(settings.DOMAIN)
    for img in images_list:
        img_src_path = os.path.join(settings.DEFAULT_DATA_DIR,
                                    img['uuid'] + '.zip')  # TODO: get the actual path on every server
        img_dest_path = os.path.join(stack_dir, img['esa_id'] + '.zip')
        img_host = img['machine'] + '.' + settings.DOMAIN

        if img_host == local_hostname:
            try:
                subprocess.run("ln -sf {src} {dest}"
                .format(src=img_src_path, dest=img_dest_path), shell=True, check=True)
            except subprocess.CalledProcessError as e:
                raise FileNotFoundError("Image {}.zip could not be found locally \n Stderr: {}"
                    .format(img['uuid'], e.stderr)) from e
        else:
            try:
                logging.info('Transferring {}.zip'.format(img['uuid']))
                subprocess.run(
                    'rsync -e "ssh -o StrictHostKeyChecking=no" -avrz data_ldap@{host}:{master_remote} {master_local}'
                        .format(host=img_host,master_remote=img_src_path, master_local=img_dest_path),
                        shell=True, check=True, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise RuntimeError("Image {}.zip could not be transferred \n Stderr: {}"
                    .format(img['uuid'], e.stderr)) from e

def copy_image_to_local(settings):
    stack_dir = settings.TEMPDIR
    makedirs_if_not_exists(stack_dir)

    local_hostname = get_normalized_hostname('localhost')

    print (local_hostname)
    print (settings)
    print (settings.DEFAULT_DATA_DIR)
    print (settings.fileName)
    img_src_path = os.path.join(settings.DEFAULT_DATA_DIR,
    settings.esa_id)  # TODO: get the actual path on every server
    img_dest_path = os.path.join(stack_dir, settings.fileName)
    img_host = settings.machine + '.' + settings.DOMAIN
    print (img_host)

    if img_host == local_hostname:
        subprocess.check_call("ln -sf {src} {dest}".format(src=img_src_path, dest=img_dest_path), shell=True)
    else:

        subprocess.check_call('rsync -e "ssh -o StrictHostKeyChecking=no" -avrz data_ldap@{host}:{master_remote} {master_local}'.format(host=img_host,
                                                                                             master_remote=img_src_path,
                                                                                             master_local=img_dest_path),
                                  shell=True)




def copy_tiff_to_ftp(settings, tiff_file_name):
    # NOTE: ftp is on images.skygeo.com which still uses the `data` user instead of `data_ldap`
    ftp_dir = settings.ftp_dir
    img_src_path = os.path.join(settings.TEMPDIR, tiff_file_name)  # TODO: get the actual path on every server
    img_host = settings.ftp_host
    if settings.wms:
        img_dest_dir = os.path.join(ftp_dir, settings.date)
        img_dest_path = os.path.join(ftp_dir, settings.date, tiff_file_name)
        subprocess.check_call("ssh data@{host} mkdir -p {master_remote}".format(
                host=img_host, master_remote=img_dest_dir),shell=True)
    else:
        img_dest_path = os.path.join(ftp_dir, tiff_file_name)

    subprocess.check_call('rsync -e "ssh -o StrictHostKeyChecking=no" -avrz {master_local} data@{host}:{master_remote}'.format(host=img_host,
       master_remote=img_dest_path,
       master_local=img_src_path),
       shell=True)

def remote_file_exists(remote_file):
    """
    Returns True if a remote file exists, False if it does not. Raises an
    exception when it can't connect.

    TODO: Might be nice to return a filesize or other stat information as
          well, could help to verify that the file is indeed the same as on
          some local place.
    """
    (remote_server, remote_path) = remote_file.split(":", maxsplit=1)
    (remote_user, remote_host) = remote_server.split("@", maxsplit=1)
    (remote_dir, _) = os.path.split(remote_path)

    # Check that the authentication is working by logging in to the
    # remote server and running 'whoami'
    cmd = ['ssh', remote_server, 'whoami']
    res = subprocess.run(cmd, stdout=subprocess.PIPE)

    if res.returncode != 0:
        raise Exception("Authentication Failed (1)")

    cmd = ['ssh', remote_server, 'test', '-f', remote_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE)

    if res.returncode == 0:
        return True
    else:
        return False

def sync_file(source, destination, create_dirs=True,
                         overwrite=True, rsync_flags='-avrz'):
    """
    Syncs a local file to a remote location using ssh and rsync. This is a
    utility function that can be used for various purposes, like generally
    moving image files around, and also for moving images to an FTP location
    on the FTP server.

    It requires SSH keys for the local 'data' user to be present on the remote
    machine in order to authenticate.

    Returns True when the final rsync command was successful.


    The function takes the following arguments:

    local_file
    Path to the local file to copy

    remote_file
    Path to the remote file to move this file to. It takes a path in the
    format: <user>@<hostname>:<path>

    create_dirs=True
    Create the remote directory if it doesn't exist yet.

    overwrite=True
    Overwrite the existing file.

    rsync_flags='-avrz'
    Rsync flags to apply to the rsync command. Leave as is unless you need
    something specific.
    """
    sync_incoming = None
    sync_outgoing = None

    if any(destination.startswith(user+"@") for user in ('deploy', 'data', 'data_ldap')):
        local_file = source
        remote_file = destination
        sync_incoming = False
        sync_outgoing = True

    if any(source.startswith(user+"@") for user in ('deploy', 'data', 'data_ldap')):
        local_file = destination
        remote_file = source
        sync_incoming = True
        sync_outgoing = False

    if not (sync_incoming or sync_outgoing):
        raise Exception("Could not determine if sync is incoming or outgoing.")
    (remote_server, remote_path) = remote_file.split(":", maxsplit=1)
    (remote_user, remote_host) = remote_server.split("@", maxsplit=1)
    (remote_dir, remote_filename) = os.path.split(remote_path)

    #if the image to be synced lives locally, symlink it to destination folder
    local_hostname = get_normalized_hostname('skygeo.com')
    if sync_incoming and remote_host == local_hostname:
        try:
            subprocess.run("cp {src} {dest}"
            .format(src=remote_path, dest=destination), shell=True, check=True)
            return
        except subprocess.CalledProcessError as e:
            raise FileNotFoundError("Image {} could not be found locally \n Stderr: {}"
                .format(remote_filename, e.stderr)) from e

    # Make sure the target directory exists
    if sync_outgoing:
        try:
            cmd = ['ssh', remote_server, 'mkdir', '-p', remote_dir]
            subprocess.run(cmd, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("Failed to create remote directory {} \ Stderr: {}". format(remote_dir, e.stderr))

    # Run the rsync command to complete the file sync
    try:
        cmd = ['rsync', rsync_flags, source, destination]
        subprocess.run(
            'rsync -e "ssh -o StrictHostKeyChecking=no" {rsync_flags} {source} {destination}'
            .format(rsync_flags=rsync_flags,source=source, destination=destination),
            shell=True, check=True, stderr=subprocess.PIPE)
    except Exception as e:
        raise RuntimeError("Image {} could not be transferred \n Stderr: {}"
            .format(remote_filename, e.stderr)) from e

def sync_multiple_files(destination, *filepath_source_and_output):
    """
    Sync multiple files to certain destination

    Parameters
    ----------
    destination: string
        full directory destination including hostname
    file_source_and_destination: tuple
        Tuples containing the source filepath and output filename
    """
    for source_file, output_filename in filepath_source_and_output:
        output_destination_path = destination + output_filename
        logger.info("Transferring file: {local_file} -> {remote_file}".format(
            local_file=source_file, remote_file=output_destination_path))
        sync_file(source_file, output_destination_path)
