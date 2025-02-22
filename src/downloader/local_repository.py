# Copyright (c) 2021-2022 José Manuel Barroso Galindo <theypsilon@gmail.com>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# You can download the latest version of this tool from:
# https://github.com/MiSTer-devel/Downloader_MiSTer
from downloader.constants import FILE_downloader_storage_zip, FILE_downloader_log, \
    FILE_downloader_last_successful_run, K_CONFIG_PATH, K_BASE_SYSTEM_PATH, \
    FILE_downloader_external_storage, K_LOGFILE, FILE_downloader_storage_json
from downloader.local_store_wrapper import LocalStoreWrapper
from downloader.other import UnreachableException, empty_store_without_base_path
from downloader.store_migrator import make_new_local_store


class LocalRepository:
    def __init__(self, config, logger, file_system, store_migrator, external_drives_repository):
        self._config = config
        self._logger = logger
        self._file_system = file_system
        self._store_migrator = store_migrator
        self._external_drives_repository = external_drives_repository
        self._storage_path_save_value = None
        self._storage_path_old_value = None
        self._storage_path_load_value = None
        self._last_successful_run_value = None
        self._logfile_path_value = None

    @property
    def _storage_save_path(self):
        if self._storage_path_save_value is None:
            self._storage_path_save_value = f'{self._config[K_BASE_SYSTEM_PATH]}/{FILE_downloader_storage_json}'
        return self._storage_path_save_value

    @property
    def _storage_old_path(self):
        if self._storage_path_old_value is None:
            self._storage_path_old_value = f'{self._config[K_BASE_SYSTEM_PATH]}/{FILE_downloader_storage_zip}'
        return self._storage_path_old_value

    @property
    def _storage_load_path(self):
        if self._storage_path_load_value is None:
            if self._file_system.is_file(self._storage_old_path):
                store_path = self._storage_old_path
            else:
                store_path = self._storage_save_path
            self._storage_path_load_value = store_path
        return self._storage_path_load_value

    @property
    def _last_successful_run(self):
        if self._last_successful_run_value is None:
            self._last_successful_run_value = '%s/%s' % (self._config[K_BASE_SYSTEM_PATH], FILE_downloader_last_successful_run % self._config[K_CONFIG_PATH].stem)
        return self._last_successful_run_value

    @property
    def logfile_path(self):
        if self._logfile_path_value is None:
            if self._config[K_LOGFILE] is not None:
                self._logfile_path_value = self._config[K_LOGFILE]
            else:
                self._logfile_path_value = '%s/%s' % (self._config[K_BASE_SYSTEM_PATH], FILE_downloader_log % self._config[K_CONFIG_PATH].stem)
        return self._logfile_path_value

    def set_logfile_path(self, value):
        self._logfile_path_value = value

    def load_store(self):
        self._logger.bench('Loading store...')

        if self._file_system.is_file(self._storage_load_path):
            try:
                local_store = self._file_system.load_dict_from_file(self._storage_load_path)
            except Exception as e:
                self._logger.debug(e)
                self._logger.print('Could not load store')
                local_store = make_new_local_store(self._store_migrator)
        else:
            local_store = make_new_local_store(self._store_migrator)

        self._store_migrator.migrate(local_store)  # exception must be fixed, users are not modifying this by hand

        external_drives = self._store_drives()

        for drive in external_drives:
            external_store_file = '%s/%s' % (drive, FILE_downloader_external_storage)
            if not self._file_system.is_file(external_store_file):
                continue

            try:
                external_store = self._file_system.load_dict_from_file(external_store_file)
                self._store_migrator.migrate(external_store)  # not very strict with exceptions, because this file is easier to tweak
            except UnreachableException as e:
                raise e
            except Exception as e:
                self._logger.debug(e)
                self._logger.print('Could not load external store for drive "%s"' % drive)
                continue

            for db_id, external in external_store['dbs'].items():
                if db_id not in local_store['dbs'] or len(local_store['dbs'][db_id]) == 0:
                    local_store['dbs'][db_id] = empty_store_without_base_path()
                local_store['dbs'][db_id]['external'] = local_store['dbs'][db_id].get('external', {})
                local_store['dbs'][db_id]['external'][drive] = external

        return LocalStoreWrapper(local_store)

    def has_last_successful_run(self):
        return self._file_system.is_file(self._last_successful_run)

    def _store_drives(self):
        return self._external_drives_repository.connected_drives_except_base_path_drives(self._config)

    def save_store(self, local_store_wrapper):
        if not local_store_wrapper.needs_save():
            self._logger.debug('Skipping local_store saving...')
            return

        local_store = local_store_wrapper.unwrap_local_store()
        external_stores = {}
        for db_id, store in local_store['dbs'].items():
            if 'external' not in store:
                continue

            for drive, external in store['external'].items():
                if drive not in external_stores:
                    external_stores[drive] = make_new_local_store(self._store_migrator)
                    external_stores[drive]['internal'] = False

                external_stores[drive]['dbs'][db_id] = external

            del store['external']

        self._file_system.make_dirs_parent(self._storage_save_path)
        self._file_system.save_json(local_store, self._storage_save_path)
        if self._file_system.is_file(self._storage_old_path) and \
                self._file_system.is_file(self._storage_save_path, use_cache=False):
            self._file_system.unlink(self._storage_old_path)

        external_drives = set(self._store_drives())

        for drive, store in external_stores.items():
            self._file_system.save_json(store, '%s/%s' % (drive, FILE_downloader_external_storage))
            if drive in external_drives:
                external_drives.remove(drive)

        for drive in external_drives:
            db_to_clean = '%s/%s' % (drive, FILE_downloader_external_storage)
            if self._file_system.is_file(db_to_clean):
                self._file_system.unlink(db_to_clean)

        self._file_system.touch(self._last_successful_run)

    def save_log_from_tmp(self, path):
        self._file_system.turn_off_logs()
        self._file_system.make_dirs_parent(self.logfile_path)
        self._file_system.copy(path, self.logfile_path)


class LocalRepositoryProvider:
    def __init__(self):
        self._local_repository = None

    def initialize(self, local_repository):
        if self._local_repository is not None:
            raise LocalRepositoryProviderException("Shouldn't initialize self twice.")

        self._local_repository = local_repository

    @property
    def local_repository(self):
        if self._local_repository is None:
            raise LocalRepositoryProviderException("Can't get a local repository before initializing self.")

        return self._local_repository


class LocalRepositoryProviderException(Exception):
    pass
