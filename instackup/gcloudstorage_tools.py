import os
import logging
import pandas as pd
from google.cloud import storage
from instackup.general_tools import fetch_credentials


# Logging Configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s: %(message)s")

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(LOG_DIR, "gcloudstorage_tools.log"))
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


def parse_gs_path(gs_path):
    """Parses a Google Cloud Storage (GS) path into bucket and subfolder(s).
    Raises an error if GS path is with wrong format."""

    # If there isn't at least 3 "/" in the path, it will default to only set bucket name.
    # If there isn't at least 2 "/" in the path, the path has a syntax error.
    try:
        gs_pattern, _, bucket, subfolder = gs_path.split("/", 3)
    except ValueError:
        try:
            gs_pattern, _, bucket = gs_path.split("/", 2)
        except ValueError:
            logger.error(f"Invalid Google Cloud Storage full path '{gs_path}'!")
            raise ValueError(f"Invalid Google Cloud Storage full path '{gs_path}'! Format should be like 'gs://<bucket>/<subfolder>/'")
        else:
            subfolder = ""

    # Clean subfolder into something it will not crash a method later
    if len(subfolder) != 0 and not subfolder.endswith("/"):
        subfolder += "/"

    logger.debug(f"gs_pattern: '{gs_pattern}', bucket: '{bucket}', subfolder: '{subfolder}'")

    # Check for valid path
    if gs_pattern != "gs:":
        logger.error(f"Invalid Google Cloud Storage full path '{gs_path}'!")
        raise ValueError(f"Invalid Google Cloud Storage full path '{gs_path}'! Format should be like 'gs://<bucket>/<subfolder>/'")

    return bucket, subfolder


class GCloudStorageTool(object):
    """This class handle most of the interaction needed with Google Cloud Storage,
    so the base code becomes more readable and straightforward."""

    def __init__(self, bucket=None, subfolder="", gs_path=None):
        if all(param is not None for param in [bucket, gs_path]):
            logger.error("Specify either bucket name or full Google Cloud Storage path.")
            raise ValueError("Specify either bucket name or full Google Cloud Storage path.")

        # If a gs_path is set, it will find the bucket and subfolder.
        # Even if all parameters are set, it will overwrite the given bucket and subfolder parameters.
        # That means it will have a priority over the other parameters.
        if gs_path is not None:
            bucket, subfolder = parse_gs_path(gs_path)

        # Getting credentials
        google_creds = fetch_credentials("Google")
        connect_file = google_creds["secret_filename"]
        credentials_path = fetch_credentials("credentials_path")

        # Sets environment if not yet set
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is None:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(credentials_path, connect_file)

        # Initiating client
        logger.debug("Initiating Google Cloud Storage Client")
        try:
            storage_client = storage.Client()
            logger.info("Connected.")
        except Exception as e:
            logger.exception("Error connecting with Google Cloud Storage!")
            raise e

        self.client = storage_client
        self.bucket_name = bucket
        self.subfolder = subfolder
        self.blob = None

    @property
    def bucket(self):
        self._bucket = self.client.get_bucket(self.bucket_name)
        return self._bucket

    def set_bucket(self, bucket):
        self.bucket_name = bucket

    def set_subfolder(self, subfolder):
        self.subfolder = subfolder

    def set_blob(self, blob):

        # Tries to parse as a gs path. If it fails, ignores this part
        # and doesn't change the value of remote_path parameter
        try:
            bucket, blob = parse_gs_path(blob)
        except ValueError:
            pass
        else:
            if bucket != self.bucket_name:
                logger.warning("Path given has different bucket than the one that is currently set. Ignoring bucket from path.")
                print("WARNING: Path given has different bucket than the one that is currently set. Ignoring bucket from path.")

            # parse_gs_path() function adds a "/" after a subfolder.
            # Since this is a file, the "/" must be removed.
            blob = blob[:-1]

        self.blob = self.bucket.blob(blob)

    def set_by_path(self, gs_path):
        self.bucket_name, self.subfolder = parse_gs_path(gs_path)

    def get_gs_path(self):
        if self.blob is None:
            return f"gs://{self.bucket_name}/{self.subfolder}"
        else:
            return f"gs://{self.bucket_name}/{self.blob.name}"

    def list_all_buckets(self):
        """Returns a list of all Buckets in Google Cloud Storage"""

        return [self.get_bucket_info(bucket) for bucket in self.client.list_buckets()]

    def get_bucket_info(self, bucket=None):
        if bucket is None:
            bucket = self.bucket

        return {
            'Name': bucket.name,
            'TimeCreated': bucket._properties.get('timeCreated', ''),
            'TimeUpdated': bucket._properties.get('updated', ''),
            'OwnerID': '' if not bucket.owner else bucket.owner.get('entityId', '')
        }

    def list_bucket_attributes(self):
        """A list of all curently supported bucket attributes that comes in get_bucket_info method return dictionary."""

        return [
            "Name",
            "TimeCreated",
            "TimeUpdated",
            "OwnerID"
        ]

    def get_blob_info(self, blob=None, param=None):
        """Converts a google.cloud.storage.Blob (which represents a storage object) to context format (GCS.BucketObject)."""
        if blob is None:
            blob = self.blob

        blob_info = {
            'Name': blob.name,
            'Bucket': blob.bucket.name,
            'ContentType': blob.content_type,
            'TimeCreated': blob.time_created,
            'TimeUpdated': blob.updated,
            'TimeDeleted': blob.time_deleted,
            'Size': blob.size,
            'MD5': blob.md5_hash,
            'OwnerID': '' if not blob.owner else blob.owner.get('entityId', ''),
            'CRC32c': blob.crc32c,
            'EncryptionAlgorithm': blob._properties.get('customerEncryption', {}).get('encryptionAlgorithm', ''),
            'EncryptionKeySHA256': blob._properties.get('customerEncryption', {}).get('keySha256', ''),
        }

        if param is not None:
            return blob_info[param]
        return blob_info

    def list_blob_attributes(self):
        """A list of all curently supported bucket attributes that comes in get_blob_info method return dictionary."""

        return [
            'Name',
            'Bucket',
            'ContentType',
            'TimeCreated',
            'TimeUpdated',
            'TimeDeleted',
            'Size',
            'MD5',
            'OwnerID',
            'CRC32c',
            'EncryptionAlgorithm',
            'EncryptionKeySHA256'
        ]

    def list_contents(self, yield_results=False):
        """Lists all files that correspond with bucket and subfolder set at the initialization.
        It can either return a list or yield a generator.
        Lists can be more familiar to use, but when dealing with large amounts of data,
        yielding the results may be a better option in terms of efficiency.

        For more information on how to use generators and yield, check this video:
        https://www.youtube.com/watch?v=bD05uGo_sVI"""

        if yield_results:
            logger.debug("Yielding the results")

            def list_contents_as_generator(self):
                if self.subfolder == "":
                    logger.debug("No subfolder, yielding all files in bucket")

                    for blob in self.client.list_blobs(self.bucket_name):
                        yield self.get_blob_info(blob)

                else:
                    logger.debug(f"subfolder '{self.subfolder}' found, yielding all matching files in bucket")

                    for blob in self.client.list_blobs(self.bucket_name, prefix=self.subfolder):
                        blob_dict = self.get_blob_info(blob)
                        if blob_dict["Name"] != self.subfolder:
                            yield blob_dict

            return list_contents_as_generator(self)

        else:
            logger.debug("Listing the results")

            contents = []

            if self.subfolder == "":
                logger.debug("No subfolder, listing all files in bucket")

                for blob in self.client.list_blobs(self.bucket_name):
                    contents.append(self.get_blob_info(blob))

            else:
                logger.debug(f"subfolder '{self.subfolder}' found, listing all matching files in bucket")

                for blob in self.client.list_blobs(self.bucket_name, prefix=self.subfolder):
                    blob_dict = self.get_blob_info(blob)
                    if blob_dict["Name"] != self.subfolder:
                        contents.append(blob_dict)

            return contents

    def upload_file(self, filename, remote_path=None):
        """Uploads file to remote path in Google Cloud Storage (GS).

        remote_path can take either a full GS path or a subfolder only one.

        If the remote_path parameter is not set, it will default to whatever subfolder
        is set in instance of the class plus the file name that is being uploaded."""

        if remote_path is None:
            remote_path = self.subfolder + os.path.basename(filename)
        else:
            # Tries to parse as a S3 path. If it fails, ignores this part
            # and doesn't change the value of remote_path parameter
            try:
                bucket, subfolder = parse_gs_path(remote_path)
            except ValueError:
                pass
            else:
                if bucket != self.bucket_name:
                    logger.warning("Path given has different bucket than the one that is currently set. Ignoring bucket from path.")
                    print("WARNING: Path given has different bucket than the one that is currently set. Ignoring bucket from path.")

                # parse_gs_path() function adds a "/" after a subfolder.
                # Since this is a file, the "/" must be removed.
                remote_path = subfolder[:-1]

        blob = self.bucket.blob(remote_path)
        print('Uploading file {} to gs://{}/{}'.format(filename, self.bucket_name, remote_path))

        blob.upload_from_filename(filename)

    def upload_subfolder(self, folder_path):
        """Uploads a local folder to with prefix as currently set enviroment (bucket and subfolder).
        Keeps folder structure as prefix in Google Cloud Storage.
        Behaves as if it was downloading an entire folder to current path."""

        # Still in development
        raise NotImplementedError

    def download_file(self, fullfilename=None, replace=False):
        """Downloads remote gs file to local path.

        If the fullfilename parameter is not set, it will default to the currently set blob.

        If replace is set to True and there is already a file downloaded with the same filename and path,
        it will replace the file. Otherwise it will create a new file with a number attached to the end."""

        if self.blob is None:
            raise ValueError

        if fullfilename is None:
            fullfilename = self.get_blob_info(param="Name")

        logger.debug(f"fullfilename: {fullfilename}")

        path, filename = os.path.split(fullfilename)
        logger.debug(f"Path: {path}")
        logger.debug(f"Filename: {filename}")

        # If this filename exists in this directory (yes, the one where this code lays), aborts the download
        if filename in next(os.walk(os.getcwd()))[2]:
            logger.error("File already exists at {}. Clean the folder to continue.".format(os.path.join(os.getcwd(), filename)))
            raise FileExistsError("File already exists at {}. Clean the folder to continue.".format(os.path.join(os.getcwd(), filename)))

        # Downloads the file
        self.blob.download_to_filename(filename)

        logger.info("Download to temporary location finished successfully")

        # Move the downloaded file to specified directory
        os.makedirs(path, exist_ok=True)
        if os.path.exists(fullfilename) and not replace:
            temp_path, ext = os.path.splitext(fullfilename)
            i = 1
            while os.path.exists(f"{temp_path}_copy_{i}{ext}"):
                i += 1
            fullfilename = f"{temp_path}_copy_{i}{ext}"
            logger.info(f"File renamed to {fullfilename}")
        os.replace(filename, fullfilename)

        logger.info("File moved successfully")
        print("Download finished successfully")

    def download_subfolder(self):
        """Downloads remote Storage files in currently set enviroment (bucket and subfolder).
        Behaves as if it was downloading an entire folder to current path."""

        # Still in development
        raise NotImplementedError

    def download_on_dataframe(self, sep=",", encoding="utf-8", decimal="."):
        """Use blob information to download file and use it directly on a Pandas DataFrame
        without having to save the file.
        """

        if self.blob is None:
            raise ValueError

        logger.debug(f"gs path: {self.get_gs_path()}")
        return pd.read_csv(self.get_gs_path(), sep=sep, encoding=encoding, decimal=decimal)
