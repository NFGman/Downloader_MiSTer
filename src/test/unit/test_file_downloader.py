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

import unittest

from downloader.constants import FILE_MiSTer, FILE_MiSTer_new, K_BASE_PATH, K_BASE_SYSTEM_PATH
from downloader.target_path_repository import downloader_in_progress_postfix
from test.fake_file_system_factory import fs_data, FileSystemFactory
from test.fake_file_downloader import FileDownloader
from test.objects import file_menu_rbf, hash_menu_rbf, file_one, hash_one, hash_MiSTer, hash_big, file_big, \
    hash_updated_big, big_size


class TestFileDownloader(unittest.TestCase):

    def setUp(self) -> None:
        self.sut = FileDownloader(file_system=FileSystemFactory(config={K_BASE_PATH: '/installed', K_BASE_SYSTEM_PATH: '/installed_system'}).create_for_system_scope())

    def test_download_nothing___from_scratch_no_issues___nothing_downloaded_no_errors(self):
        self.sut.download_files(False)
        self.assertDownloaded([])

    def test_download_files_one___from_scratch_no_issues___returns_correctly_downloaded_one_and_no_errors(self):
        self.download_one()
        self.assertDownloaded([file_one], [file_one])

    def test_download_files_one___from_scratch_with_retry___returns_correctly_downloaded_one_and_no_errors(self):
        self.sut.test_data.errors_at(file_one, 2)
        self.download_one()
        self.assertDownloaded([file_one], [file_one, file_one])

    def test_download_big_file___when_big_file_already_present_with_different_hash___gets_downloaded_through_a_downloader_in_progress_file_and_then_correctly_installed(self):
        downloader_in_progress_file = file_big + downloader_in_progress_postfix
        self.sut.file_system.test_data.with_file(file_big, {'hash': hash_big})

        self.download_big_file(hash_updated_big)
        self.assertEqual(
            fs_data(
                files={file_big: {'hash': hash_updated_big, 'size': big_size}},
                base_path='/installed'
            ),
            self.sut.file_system.data
        )
        self.assertEqual([
            {"scope": "copy", "data": ('/installed/' + downloader_in_progress_file, '/installed/' + file_big)},
            {"scope": "unlink", "data": '/installed/' + downloader_in_progress_file},
        ], self.sut.file_system.write_records)

    def test_download_files_one___from_scratch_could_not_download___return_errors(self):
        self.sut.test_data.errors_at(file_one)
        self.download_one()
        self.assertDownloaded([], run=[file_one, file_one, file_one, file_one], errors=[file_one])

    def test_download_files_one___from_scratch_no_matching_hash___return_errors(self):
        self.sut.test_data.brings_file(file_one, {'hash': 'wrong'})
        self.download_one()
        self.assertDownloaded([], run=[file_one, file_one, file_one, file_one], errors=[file_one])

    def test_download_files_one___from_scratch_no_file_exists___return_errors(self):
        self.sut.test_data.misses_file(file_one)
        self.download_one()
        self.assertDownloaded([], run=[file_one, file_one, file_one, file_one], errors=[file_one])

    def test_download_reboot_file___from_scratch_no_issues___needs_reboot(self):
        self.download_reboot()
        self.assertDownloaded([file_menu_rbf], [file_menu_rbf], need_reboot=True)

    def test_download_reboot_file___update_no_issues___needs_reboot(self):
        self.sut.file_system.add_system_path(file_menu_rbf)
        self.sut.file_system.test_data.with_file(file_menu_rbf, {'hash': 'old', 'size': 23})
        self.download_reboot()
        self.assertDownloaded([file_menu_rbf], [file_menu_rbf], need_reboot=True)

    def test_download_reboot_file___no_changes_no_issues___no_need_to_reboot(self):
        self.sut.file_system.add_system_path(file_menu_rbf)
        self.sut.file_system.test_data.with_file(file_menu_rbf, {'hash': hash_menu_rbf})
        self.download_reboot()
        self.assertDownloaded([file_menu_rbf])

    def test_download_mister_file___from_scratch_no_issues___stores_it_as_mister(self):
        self.sut.file_system.add_system_path(FILE_MiSTer)
        self.sut.file_system.test_data.with_old_mister_binary()
        self.sut.queue_file({'url': 'https://fake.com/bar', 'hash': hash_MiSTer, 'reboot': True, 'path': 'system'}, FILE_MiSTer)
        self.sut.download_files(False)
        self.assertDownloaded([FILE_MiSTer], [FILE_MiSTer], need_reboot=True)
        self.assertTrue(self.sut.file_system.is_file(FILE_MiSTer))

    def test_download_mister_file___from_scratch_no_issues___adds_the_three_mister_files_on_system_paths(self):
        self.sut.file_system.add_system_path(FILE_MiSTer)
        self.sut.file_system.test_data.with_old_mister_binary()
        self.sut.queue_file({'url': 'https://fake.com/bar', 'hash': hash_MiSTer, 'reboot': True, 'path': 'system'}, FILE_MiSTer)
        self.sut.download_files(False)
        self.assertEqual([FILE_MiSTer, FILE_MiSTer_new, self.sut.local_repository.old_mister_path], list(self.sut.file_system.data['system_paths']))

    def assertDownloaded(self, oks, run=None, errors=None, need_reboot=False):
        self.assertEqual(oks, self.sut.correctly_downloaded_files())
        self.assertEqual(errors if errors is not None else [], self.sut.errors())
        self.assertEqual(run if run is not None else [], self.sut.run_files())
        self.assertEqual(need_reboot, self.sut.needs_reboot())

    def download_one(self):
        self.sut.queue_file({'url': 'https://fake.com/bar', 'hash': hash_one}, file_one)
        self.sut.download_files(False)

    def download_big_file(self, hash_value):
        self.sut.queue_file({'url': 'https://fake.com/huge', 'hash': hash_value, 'size': big_size}, file_big)
        self.sut.download_files(False)

    def download_reboot(self):
        self.sut.queue_file({'url': 'https://fake.com/bar', 'hash': hash_menu_rbf, 'reboot': True, 'path': 'system', 'size': 23}, file_menu_rbf)
        self.sut.download_files(False)
