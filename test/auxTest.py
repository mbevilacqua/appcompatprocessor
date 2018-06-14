import os
import ntpath
import settings
import random
import tempfile
import appDB
import unicodedata
import logging
from collections import defaultdict
from appAux import update_progress

try:
    from faker import Factory
    from faker.providers import BaseProvider
except ImportError:
    if settings.__FAKER__:
        settings.__FAKER__ = False
    raise ImportError
else: settings.__FAKER__ = True

settings.init()
logger = logging.getLogger(__name__)


class WeightedRandomizer:
    def __init__ (self, weights):
        self.__max = .0
        self.__weights = []
        for value, weight in weights.items ():
            self.__max += weight
            self.__weights.append ( (self.__max, value) )

    def random (self):
        r = random.random () * self.__max
        for ceil, value in self.__weights:
            if ceil > r: return int(value)


class ACPProvider(BaseProvider):

    def gen_filename(self):
        file_extensions = ['bat','cmd','com','cpl','dat','dll','exe','msc','msi','scr','tmp','vbs']
        return os.path.splitext(fake.file_name(category=None, extension=None))[0] + "." + random.choice(file_extensions)

    def path(self):
        data_drives = ['C', 'C', 'C', 'C', 'C', 'C', 'C', 'C', 'C', 'C', 'D', 'E', 'F']
        data_paths = {}
        data_paths[''] = ['$Recycle.Bin','$RECYCLE.BIN','Documents and Settings', 'Users', 'EMC','EMC Files','EMC Reports','hp','Inetpub','Program Files','Program Files (x86)','ProgramData','Windows','Windows.old','Winnt']
        data_paths['Windows'] = ['Application', 'ccmcache', 'ccmsetup', 'Cluster', 'discagnt', 'Installer', 'Microsoft', 'PCHealth','SoftwareDistribution', 'System32', 'SysWOW64', 'Temp', 'WinSxS']
        data_paths['Windows.old'] = ['Application', 'ccmcache', 'ccmsetup', 'Cluster', 'discagnt', 'Installer', 'Microsoft', 'PCHealth','SoftwareDistribution', 'System32', 'SysWOW64', 'Temp', 'WinSxS']
        data_paths['Winnt'] = ['Application', 'ccmcache', 'ccmsetup', 'Cluster', 'discagnt', 'Installer', 'Microsoft', 'PCHealth','SoftwareDistribution', 'System32', 'SysWOW64', 'Temp', 'WinSxS']
        data_paths['Program Files'] = ['Adobe','Altiris','Apache','Blue','BMC','Citrix','Common','Dell','DisplayLink','EMC','HBAnyware','HP','IBM','IIS','InstallShield','Internet','Java','JBoss','Legato','Mirosoft','Mozilla','MySQL','OmniBack','Outlook','Reuters','RSA','SAS','SmartDraw','SplunkUniversalForwarder','Symantec','Symmetricom','System','TeraCopy','Trend','Tripwie','Unlocker','Virtual','VMware','WinAutomation','Windows','WinRAR','WinSCP','WinZip','Wireshark']
        data_paths['Program Files (x86)'] = ['Adobe','Altiris','Apache','Blue','BMC','Citrix','Common','Dell','DisplayLink','EMC','HBAnyware','HP','IBM','IIS','InstallShield','Internet','Java','JBoss','Legato','Mirosoft','Mozilla','MySQL','OmniBack','Outlook','Reuters','RSA','SAS','SmartDraw','SplunkUniversalForwarder','Symantec','Symmetricom','System','TeraCopy','Trend','Tripwie','Unlocker','Virtual','VMware','WinAutomation','Windows','WinRAR','WinSCP','WinZip','Wireshark']
        data_paths['Documents and Settings'] = ['Administrator','All Users','Default User']
        data_paths['Users'] = ['Administrator','All Users','Default User']
        data_paths['Administrator'] = ['Application Data','Desktop','Local Settings','My Documents','Start Menu']
        data_paths['All Users'] = ['Application Data','Desktop','Local Settings','My Documents','Start Menu']
        data_paths['Default Users'] = ['Application Data','Desktop','Local Settings','My Documents','Start Menu']
        data_paths['Application Data'] = ['Google','Microsoft','Microsoft Office','Skype','uTorrent']
        data_paths['Local Settings'] = ['Application','Apps','Temp']
        data_paths['Inetpub'] = ['sites','wwwroot']


        # Number of folders weighted distribution extracted from a 3K host database
        folderNumWeightedDistribution = {'14': 0.035, '13': 0.07, '12': 0.125, '11': 0.485, '10': 1.025, '9': 72.205, '8': 66.805, '7': 30.35,
             '6': 170.38, '5': 48.83, '4': 30.165, '3': 102.39, '2': 23.245, '1': 286.27}
        folderNumWeightedRandomizer = WeightedRandomizer(folderNumWeightedDistribution)

        file_name = ""
        # Assign drive
        file_name += (random.choice(data_drives)) + ":"
        # Build path
        current_subpath = ''
        for i in xrange(1, folderNumWeightedRandomizer.random()):
            if current_subpath in ['Documents and Settings', 'Users']:
                current_subpath = fake.name().replace(' ','_')
            elif current_subpath in data_paths:
                current_subpath = (random.choice(data_paths[current_subpath]))
            else:
                current_subpath =  os.path.splitext(fake.file_name(category=None, extension=None))[0]
            file_name += "\\" + current_subpath

        # Add file
        file_name += "\\" + self.gen_filename()
        return file_name



fake = Factory.create()
fake_ES = Factory.create('es_ES')
# Add new provider to faker instance
fake.add_provider(ACPProvider)


def strip_non_ascii(string):
    ''' Returns the string without non ASCII characters'''
    stripped = (c for c in string if 0 < ord(c) < 127)
    return ''.join(stripped).replace("'", "")

def strip_accents(s):
   return ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn')


def add_entry(DB, HostName, entry_fields):

    # Insert host if it doesn't exist
    Instances = []
    InstancesCounter = 0
    Recon = 0
    ReconScoring = 0
    DB.ExecuteMany("INSERT OR IGNORE INTO Hosts VALUES (NULL,?,?,?,?,?)",
                   [(HostName, str(repr(Instances)), InstancesCounter, Recon, ReconScoring)])
    # Get HostID
    HostID = DB.Query("SELECT HostID FROM Hosts WHERE HostName = '%s'" % HostName)[0][0]

    # Add FilePath if not there yet
    DB.Execute("INSERT OR IGNORE INTO FilePaths VALUES (NULL, '%s')" % entry_fields.FilePath)
    # Get FilePathID
    FilePathID = DB.QueryInt("SELECT FilePathID FROM FilePaths WHERE FilePath = '%s'" % entry_fields.FilePath)

    insertList = []
    insertList.append((HostID, entry_fields.EntryType, entry_fields.RowNumber, entry_fields.LastModified,
                       entry_fields.LastUpdate, FilePathID, entry_fields.FileName, entry_fields.Size,
                       entry_fields.ExecFlag, entry_fields.SHA1, entry_fields.FileDescription, entry_fields.FirstRun,
                       entry_fields.Created, entry_fields.Modified1, entry_fields.Modified2, entry_fields.LinkerTS,
                       entry_fields.Product, entry_fields.Company, entry_fields.PE_sizeofimage, entry_fields.Version_number,
                       entry_fields.Version, entry_fields.Language, entry_fields.Header_hash, entry_fields.PE_checksum,
                       entry_fields.SwitchBackContext, entry_fields.InstanceID))

    numFields = 29 - 3
    valuesQuery = "(NULL," + "?," * numFields + "0, 0)"
    DB.ExecuteMany("INSERT INTO Entries VALUES " + valuesQuery, insertList)


def build_fake_DB(hosts = 10, seed = random.randint(0,10000), database_file = None):
    hostnames_set = set()
    filePaths_dict = defaultdict(int)
    filePaths_dict_ID = 0
    filePaths_dict_ID_skip = 0

    random.seed(seed)
    fake.seed(seed)
    fake_ES.seed(seed)

    if database_file == None:
        # Get temp db name for the test
        tempdb = tempfile.NamedTemporaryFile(suffix='.db', prefix='testCase', dir=tempfile.gettempdir())
        tempdb.close()
        database_file = tempdb.name

    if os.path.isfile(database_file):
        logger.warning("Adding hosts to existing database")
        with appDB.DBClass(database_file, "False", settings.__version__) as DB:
            conn = DB.appConnectDB()
            # Load existing hosts
            data = DB.Query("SELECT HostName FROM Hosts")
            for hostName in data:
                hostnames_set.add(hostName[0])
            # Load existing paths
            data = DB.Query("SELECT FilePathID, FilePath FROM FilePaths")
            for filePathID, FilePath in data:
                filePaths_dict[FilePath] = (filePathID)
                filePaths_dict_ID += 1
            filePaths_dict_ID_skip = filePaths_dict_ID

    else:
        with appDB.DBClass(database_file, "True", settings.__version__) as DB:
            DB.appInitDB()
            DB.appSetIndex()
            conn = DB.appConnectDB()
            DB.appRequireIndexesDB("index_EntriesHostName", "CREATE INDEX index_EntriesHostName on Hosts(HostName)")
            DB.appRequireIndexesDB("index_FilePathsFilePath", "CREATE INDEX index_FilePathsFilePath on FilePaths(FilePath)")

    with appDB.DBClass(database_file, "False", settings.__version__) as DB:
        conn = DB.appConnectDB()

        # Start creating hosts and data:
        rowList = []
        insertList = []
        numFields = 29 - 3
        valuesQuery = "(NULL," + "?," * numFields + "0, 0)"

        progressCurrent = 0
        progressTotal = hosts
        for i in xrange(0,hosts):
            progressCurrent += 1
            update_progress(float(progressCurrent) / float(progressTotal))

            HostName = ""
            while True:
                HostName = strip_accents((fake_ES.color_name() + fake_ES.country()).replace(' ', ''))
                HostName = strip_non_ascii(HostName)
                HostName += "_" + str(random.randint(000,999))
                if HostName not in hostnames_set:
                    hostnames_set.add(HostName)
                    break

            print "Creating appcompat/amcache data for host: %s" % HostName
            Instances = ['dummy']
            InstancesCounter = 1
            Recon = 0
            ReconScoring = 0

            DB.ExecuteMany("INSERT INTO Hosts VALUES (NULL,?,?,?,?,?)", [(HostName, str(repr(Instances)), InstancesCounter, Recon, ReconScoring)])
            HostID = DB.Query("SELECT HostID FROM Hosts WHERE HostName = '%s'" % HostName)[0][0]

            # Sampled 2K hosts, this should statistically provide a somewhat realistic amount of entries (for AppCompat)
            for i in xrange(1, random.randint(400,800)):
                # EntryType = random.choice([settings.__APPCOMPAT__,settings.__AMCACHE__])
                EntryType = settings.__APPCOMPAT__
                RowNumber = 0
                LastModified = str(fake.date_time_between('-1y')) + "." + str(random.randint(1,9999))
                LastUpdate = str(fake.date_time_between('-4y')) + "." + str(random.randint(1,9999))
                filePathID = 0
                # todo: FilePath retains final backslash on root paths (c:\, d:\ ...) remove.
                FilePath, FileName = ntpath.split(fake.path())
                FilePath = FilePath.lower()
                FileName = FileName.lower()
                Size = random.randint(1,100000)
                if EntryType == settings.__APPCOMPAT__:
                    ExecFlag = random.choice(['True','False'])
                else: ExecFlag = 'True'

                if EntryType == settings.__AMCACHE__:
                    SHA1 = fake.sha1()
                    FileDescription = random.choice(['', '', '', '', '', '', '', '', '', '', fake.text()])
                    FirstRun = str(fake.date_time_between('-1y')) + "." + str(random.randint(1,9999))
                    Created = str(fake.date_time_between('-5y')) + "." + str(random.randint(1,9999))
                    Modified1 = str(fake.date_time_between('-5y')) + "." + str(random.randint(1,9999))
                    Modified2 = str(fake.date_time_between('-5y')) + "." + str(random.randint(1,9999))
                    LinkerTS = str(fake.date_time_between('-10y'))
                    Company = fake.company()
                    PE_sizeofimage = random.randint(1,10000)

                    # Redo re-assignment of date we do on load for AmCache
                    LastUpdate = FirstRun
                    LastModified = Modified2
                else:
                    SHA1 = ''
                    FileDescription = ''
                    FirstRun = ''
                    Created = ''
                    Modified1 = ''
                    Modified2 = ''
                    LinkerTS = ''
                    Company = ''
                    PE_sizeofimage = ''

                Product = 0
                Version_number = 0
                Version = 0
                Language = 0
                Header_hash = 0
                PE_checksum = 0
                SwitchBackContext = 0
                InstanceID = 0

                # # Add FilePath if not there yet
                # DB.Execute("INSERT OR IGNORE INTO FilePaths VALUES (NULL, '%s')" % FilePath)
                # # Get FilePathID
                # FilePathID = DB.QueryInt("SELECT FilePathID FROM FilePaths WHERE FilePath = '%s'" % FilePath)
                if FilePath not in filePaths_dict:
                    filePaths_dict[FilePath] = (filePaths_dict_ID)
                    filePathID = filePaths_dict_ID
                    filePaths_dict_ID += 1
                else: filePathID = filePaths_dict[FilePath]

                insertList.append((HostID, EntryType, RowNumber, LastModified, LastUpdate, filePathID, FileName,
                                   Size, ExecFlag, SHA1, FileDescription, FirstRun, Created, Modified1,
                                   Modified2, LinkerTS, Product, Company, PE_sizeofimage, Version_number,
                                   Version, Language, Header_hash, PE_checksum, SwitchBackContext, InstanceID))

                # Dump every now and then:
                if len(insertList) > 1000000:
                    logger.info("Dumping data to DB")
                    DB.ExecuteMany("INSERT INTO Entries VALUES " + valuesQuery, insertList)
                    insertList = []

        # Insert last bucket
        logger.info("Dumping last bucket to DB")
        DB.ExecuteMany("INSERT INTO Entries VALUES " + valuesQuery, insertList)

        # Insert new FilePaths
        list_FilePath_ID = [(v, k) for k, v in filePaths_dict.items()]
        list_FilePath_ID.sort(key=lambda tup: tup[0])
        DB.ExecuteMany("INSERT INTO FilePaths VALUES (?,?)", list_FilePath_ID[filePaths_dict_ID_skip:])

    return database_file