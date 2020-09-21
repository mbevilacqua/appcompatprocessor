**Build Status:**
- Master [![Build Status](https://travis-ci.org/mbevilacqua/appcompatprocessor.svg?branch=master)](https://travis-ci.org/mbevilacqua/appcompatprocessor)
- Develop [![Build Status](https://travis-ci.org/mbevilacqua/appcompatprocessor.svg?branch=develop)](https://travis-ci.org/mbevilacqua/appcompatprocessor)



# AppCompatProcessor (Beta)
"_Evolving AppCompat/AmCache data analysis beyond grep_"

AppCompatProcessor has been designed to extract additional value from enterprise-wide AppCompat / AmCache data beyond the classic stacking and grepping techniques.


If you don't fancy reading check the SANS Threat Hunting 2017 presentation [here](https://www.youtube.com/watch?v=-0bYcD3_bBs)

**Note: Windows platform support has been temporarily removed (expect to see it back shortly though)** 



### Installation:

**OSX**
You need Python 2.7+, libregf and pyregf (python bindings) from https://github.com/libyal/libregf

-Option A Source distribution package from https://github.com/libyal/libregf/releases
- ./configure --enable-python && make
- sudo make install
- python setup.py build
- python setup.py install

-Option B Direct from source
- git clone https://github.com/libyal/libregf.git
- cd libregf/
- ./synclibs.sh
- ./autogen.sh
- ./configure --enable-python && make
- sudo make install
- python setup.py build
- python setup.py install


The rest of the requirements you can handle with 'pip install -r requirements.txt'.

**Linux**
You need Python 2.7+ and 'sudo pip install -r requirements.txt' should take care of everything for you.
If you have issues with libregf or pyregf (python bindings for libregf) you can find them here: https://github.com/libyal/libregf

Note: There seems to be an issue with some libregf versions on some linux environments in which libregf apparently provides file paths encoded in UTF16 (breaking sql inserts for us) when it used to do UTF8. Still trying to pinpoint when and why that happens to handle it correctly.

**SIFT v3 users**
Sift comes pre-packaged with libregf v20141030 so 'sudo pip install -r requirements.txt' will add the few missing pieces easily.

**Windows**
Note: ACP is currently broken on Windows due to differences in implementation of multiprocessing!


### Ingestion Modules

The following ingestion formats are currently supported:

* AppCompat in CSV format as produced by ShimCacheParser.py
> Use flags -t -o and store as one file per host.
> File naming convention that you'll need to follow: \<HOSTNAME\>.csv.
> Note that BOM is not currently supported so avoid the '--bom' flag for the time being.
* AppCompat in Redline format
> Redline creates a folder named after the hostname in the AnalysisSession1/Audits folder.
> Aggregate all those folders into a single folder that must be called 'RedlineAudits' and ingest that folder to load everything up.
* AppCompat from raw SYSTEM hives
> File names must begin by "SYSTEM".
> Host name is extracted from the hive itself.
* AmCache from raw AmCache hives
> File naming convention that you'll need to follow: \<HOSTNAME\>.hve.
* Shim Shady in-memory extraction of ShimCache records (no enrichment)
* AppCompat Mir RegistryAudit (XML)
* AppCompat Mir LUA script (XML)
* AppCompat from SYSTEM hives retrieved through a Mir FileAcquisition audit
* AmCache from AmCache.hve hives retrieved through a Mir FileAcquisition audit
* Zip files containing any of the above


### Modules:

**load 'path'**: Load (or add new) AppCompat/AmCache data from 'path'

Check [Ingestion Modules](#Ingestion Modules) for a list of supported formats
``` bash
./AppCompatProcessor.py ./database.db load ./path/to/load
```
> Load will recurse down any available folders to identify files to load.

``` bash
./AppCompatProcessor.py ./database.db load ./path/to/file.zip
```
> Load will do in-memory processing of the zip file and load its contents.

**status**: Print status of database

Provides a Host and Entry/Instance count.

**list**: List hosts in database

Lists all hosts in database including Recon scoring if available.

**search -f 'regex'**: Search for regular expression 'regex' (remember to provide shell escaping)

Search for a regex term. Search space is limited to FilePath\FileName.
Output is written to 'Output.txt' if the -o flag isn't specified to write to a custom file.

**search -F 'string'**: Search for literal 'string'

Search for a literal term. Search space is limited to FilePath\FileName.

**search ['file']**: Search for KnownBad expressions.

Designed to perform massive searches for known bad and methodology regex terms, supports filtering to reduce FPs.
Search space is limited to FilePath\FileName.
If no file is provided as an argument it will search for KnownBad expressions shipped with ACP, otherwise the provided KnownBad file will be used.
Bundled known bad expressions and filters are provided in `AppCompatSearch.txt`. When installed through setuptools the bundled 'AppCompatSearch.txt' will be deployed in `/etc/AppCompatProcessor`

Additional files matching 'AppCompatSearch-.*' can be created to supplement the default set of regular expressions with your own sets, these will automatically picked up by ACP.


> Most modules from AppCompatProcessor have been optimized and refactored to enable them to take advantage of modern multi-core processors.

``` bash
./AppCompatProcessor.py test.db search
Searching for known bad list: ./AppCompatSearch.txt (130 search terms) - SearchSpace: (FilePath || '\' || FileName) => Output.txt
Using 6 cores for searching / 1 cores for dumping results
Searching: [#########################] 100.0% Done...
Finishing dumping results to disk: [#########################] 100.0% Done...
Hit histogram:
\\..\..{1,3}$                                      120
\\Start Menu\\Programs\\Startup                    93
\\RarSFX0\\.*\.exe                                 91
\\tsclient\\                                       40
\\(rundll32|cmd|taskeng|conhost|powershell)\.exe   29
C:\\Windows\\setup\.exe                            19
\\.\..{1,3}$                                       13
\.(log|txt|dat)$                                   9
\\Music\\[^\\]*\.                                  8
\\rar\.exe                                         4
\\ProgramData\\[^\\]*\.                            4
```
> The search module will produce two files along with a hit histogram:

* Output.txt: Raw dump of hits
* Output.mmd: Dump of hits using MultiMarkDown notation to highlight expressions matched or each entry.

**fsearch 'field/list' \[\--sql] (-f/-F) '[<=>]regex/string'**: Field Search, same principle as the Search module but operating on a user supplied DB field.

'fsearch list' will print out the fields available in the Entries table against which you can search.
--sql can be used to build creative search spaces against which to search

``` bash
./AppCompatProcessor.py ./database.db fsearch list
['rowid', 'hostid', 'entrytype', 'rownumber', 'lastmodified', 'lastupdate', 'filepath', 'filename', 'size', 'execflag', 'sha1', 'filedescription', 'firstrun', 'created', 'modified1', 'modified2', 'linkerts', 'product', 'company', 'pe_sizeofimage', 'version_number', 'version', 'language', 'header_hash', 'pe_checksum', 'switchbackcontext', 'recon', 'reconsession']

./AppCompatProcessor.py ./database.db fsearch FileName -F "cmd.exe"
Will search the FileName field for anything that contains 'cmd.exe' 

./AppCompatProcessor.py ./database.db fsearch FileName -F "=cmd.exe"
Will search the FileName field for anything that exactly matches 'cmd.exe' 

./AppCompatProcessor.py ./database.db fsearch Size -F "4096"
Will find files whose size contains "4096" 

./AppCompatProcessor.py ./database.db fsearch Size -F "=4096"
Will find files whose size _is_ "4096" 

./AppCompatProcessor.py ./database.db fsearch Size -F ">4096"
Will find files whose size is bigger than 4096 bytes (and has Size data of course: XP appcompat or AmCache data)

./AppCompatProcessor.py ./test-AmCache.db fsearch Product -F "Microsoft@"
Will find files for some attackers that regularly screwed the trademark symbol on the versioning information on their tools.

./AppCompatProcessor.py ./delete.db fsearch FirstRun -F ">2015-01-18<2015-01-21"
(nope sorry, just use sqlite if you want to get that fancy!: "SELECT * FROM Csv_Dump WHERE LastModified BETWEEN '2015-01-18' and '2015-01-21'")

./AppCompatProcessor.py ./database.db fsearch FileName -f "=cm[ad].exe"
Will search the FileName field for anything that exactly matches against the regular expression '^cmd[ad].exe$' 

./AppCompatProcessor.py ./database.db fsearch --sql "(FilePath || '\\' || FileName)" -f "Windows\\hkcmd.exe"
Will search for entries who's fullpath contains Windows\hkcmd.exe. This sql tweak is exactly what happens by default with the Search module BTW.
Note: The weird syntax there is what SQL expect you to use to concatenate two fields with a backslash separator. You can use this as an example of how to build custom search spaces.
```

**filehitcount 'file'**: Count # of FileName hits from 'file'

Provides a quick count of hits for a set of filenames stored in a file.
Search space if limited to FileName only.
``` bash
./AppCompatProcessor.py ./database.db filehitcount ./path/to/file/file.txt
FileName              HitCount
cmd.exe               4098
wmiprvse.exe          2973
net.exe               2528
net1.exe              2392
schtasks.exe          2285
WMIC.exe              1791
netsh.exe             1624
ARP.EXE               1413
HOSTNAME.EXE          1364
PING.EXE              1346
ipconfig.exe          1185
vds.exe               1019
vdsldr.exe            1015
CompMgmtLauncher.exe  940
ceipdata.exe          912
ceiprole.exe          837
NETSTAT.EXE           728
ServerManagerCmd.exe  494
whoami.exe            352
tasklist.exe          284
at.exe                139
winver.exe            118
TRACERT.EXE           110
systeminfo.exe        91
quser.exe             50
dsget.exe             11
dsquery.exe           11
```
> Not a lot to explain there but that's BTW the default list of filenames used to calculate reconnaissance sessions right now.

**tcorr 'filename'**: Search for temporal execution correlations on 'filename'

Searches for files which present a high 'temporal execution correlation' with the 'filename' provided.

A high temporal execution correlation between file A and file B indicates that file B is usually executed before/after file A (think dropper -> payload)
``` bash
./AppCompatProcessor.py ./test1.db tcorr "net.exe"
Sample output:
LastModified       LastUpdate  FilePath             FileName(*)  Size  ExecFlag  Before  After  Weight    InvBond  Total_Count
11/20/10 21:29:19  N/A         C:\windows\system32  net1.exe     N/A   True      580     1170   16149.31  True     1892
07/14/09 01:14:50  N/A         C:\windows\system32  xcopy.exe    N/A   True      14      1038   5100.9    True     2264
07/14/09 01:14:19  N/A         C:\windows\system32  Dwm.exe      N/A   True      418     1      2419.38     -      2301
(*) Note that context AppCompat data is pulled from first match in DB as an example (dates, paths, sizes, of other correlating files with the same FileName could be different)
```
> Columns Before / After indicate how many times the file was observed to be executed 'before or after' the file provided.

> For each occurrence of the file we're analysing, tcorr will look at all files executed before and after within the configured recon window (defaults to 3 and can be set with the -w flag)

> 'net1.exe' was observed to run 65.296 times after running 'net.exe', note that the 176 executions observed before are due to multiple consecutive executions of 'net.exe'.

> Weight indicates how strong the temporal execution correlation is. For each correlation observed a weight is calculated which decreases exponentially as the execution 'distance' increases (think of gravity force equations).

> InvBond (inverse bond) indicates if our file was present in the tcorr results after executing a reverse temporal execution correlation. So net.exe has a strong correlation with net1.exe and net1.exe has also a strong correlation with net.exe.

> Total_Count provides the total count of occurrences of the file. Total count can be higher that Before+After count due to consecutive executions in which tcorr windows overlap.

``` bash
./AppCompatProcessor.py ./database.db tcorr "toto.exe"
Temporal execution correlation candidates for toto.exe:
LastModified       LastUpdate  FilePath                                                         FileName(*)                   Size  ExecFlag  Before  After  Weight  InvBond  Total_Count
02/03/11 07:34:28  N/A         C:\Windows\Installer\{9d587b2b-198a-4b60-a228-e1061756f0c4}      Setup.exe                     N/A   True      7       4      74.86     -      38289
07/11/13 19:42:52  N/A         C:\$Recycle.Bin                                                  tito.tmp                       N/A   True      0       4      32.5    True     11
12/10/10 10:19:08  N/A         C:\Program Files\Microsoft SQL Server\MSSQL.3\Reporting Serv...  ReportingServicesService.exe  N/A   True      2       0      20.0      -      29
(*) Note that context AppCompat data is pulled from first match in DB as an example (dates, paths, sizes, of other correlating files with the same FileName could be different)
```
> In the example above toto.exe was a piece of malware (PlugX+SOGU).

> 'Setup.exe' turned out to be the dropper filename used to deploy toto.exe by the attacker. Note that the attacker was running setup.exe from c:\Windows and not from the path observed in the above output. As the warning implies all off the data except for the actual FileName is taken from the first occurrence in the database only to provide some context (_I'm looking into improving this_)

> Note that 'Setup.exe' is not marked as having an inverse tcorr bond with toto.exe, this illustrates the fact that there's a truckload of 'setup.exe' which are not related at all with our payload and thus it's not worth your time to perform a tcorr analysis on 'setup.exe'.

> 'tito.tmp' turned out to be a credential dumper that the attacker regularly used _after_ compromissing each new asset.

The following example introduces the '--sql' flag which allows you to tweak the SQL queries performed by tcorr to fine tune what's being correlated.
On this example the attacker used file names of legit OS files (redacted) so we get a lot of noise from tcorr and no value at all. If we tweak the sql queries performed
by tcoor to focus only on files stored in C:\Windows though then we get a completely different correlation output.

``` bash
./AppCompatProcessor.py ./database.db tcorr "redacted.exe"
Searching for temporal correlations on FileName: redacted.exe => [3291 hits]
hkcmd.exe: [#########################] 100.0% Done...
igfxtray.exe: [#########################] 100.0% Done...
igfxpers.exe: [#########################] 100.0% Done...
AdobeARM.exe: [#########################] 100.0% Done...
Temporal execution correlation candidates for redacted.exe:
LastModified       LastUpdate         FilePath                                     FileName(*)   Size   ExecFlag  Before  After  Weight   InvBond  Total_Count
08/30/07 06:20:48  01/14/16 01:11:39  C:\WINDOWS\system32                          igfxtray.exe  94208  N/A       570     544    8697.92  True     3884
07/03/13 18:16:20  N/A                SYSVOL\Windows\System32                      igfxpers.exe  N/A    True      440     600    8268.68  True     3256
12/18/12 19:08:28  N/A                C:\Program Files\Common Files\Adobe\ARM\1.0  AdobeARM.exe  N/A    True      293     208    2930.9   True     3142
(*) Note that context AppCompat data is pulled from first match in DB as an example (dates, paths, sizes, of other correlating files with the same FileName could be different)

./AppCompatProcessor.py ./database.db tcorr "redacted.exe" --sql "FilePath = 'C:\Windows'" -w 10
Searching for temporal correlations on FileName: redacted.exe [FilePath = 'C:\Windows'] => [28 hits]
hkcmd.exe: [#########################] 100.0% Done...
nsfview.exe: [#########################] 100.0% Done...
Temporal execution correlation candidates for redacted.exe:
LastModified       LastUpdate  FilePath                                                         FileName(*)           Size   ExecFlag  Before  After  Weight  InvBond  Total_Count
11/19/10 21:25:34  N/A         C:\Windows\system32\wbem                                         wmiprvse.exe          N/A    True      6       5      48.65     -      2973
01/06/16 14:11:09  N/A         C:\Program Files (x86)\BigFix Enterprise\BES Client\__BESDat...  runscanner.bat        N/A    False     15      8      41.7      -      5229
02/16/07 16:40:16  N/A         C:\WINDOWS\system32                                              netstat.exe           47616  N/A       2       8      39.01     -      728
12/12/15 11:41:35  N/A         c:\windows                                                       redacted2.exe             N/A    True      2       8      36.23     -      915
11/30/05 08:00:00  N/A         C:\WINDOWS\system32                                              find.exe              13824  N/A       1       11     28.82     -      1529
04/10/09 15:27:44  N/A         C:\Windows\system32                                              logoff.exe            N/A    True      4       2      25.35     -      127
07/14/09 01:39:35  N/A         C:\Windows\system32                                              sc.exe                N/A    True      3       6      25.0      -      2953
01/06/16 01:08:56  N/A         c:\windows                                                       redacted3.exe           N/A    True      1       3      21.51   True     1
12/26/15 20:52:35  N/A         C:\Program Files (x86)\BigFix Enterprise\BES Client\LMT\CIT      checkBZIP2Status.bat  409    N/A       4       10     17.21     -      1015
07/14/09 01:14:27  N/A         C:\Windows\system32                                              netsh.exe             N/A    False     0       4      16.11     -      1624
(*) Note that context AppCompat data is pulled from first match in DB as an example (dates, paths, sizes, of other correlating files with the same FileName could be different)
```
> 'redacted2.exe' and 'redacted3.exe' in the above output were both attacker tools.

> '-w 10' expands the recon window to 10. By default the recon windows used for AppCompat is 5 meaning 5 lines above/below.

> When running tcorr on AmCache the recon window is multiplied by 2 and interpreted as minutes before / after for correlation purposes.

**ptcorr 'filename'**: Print temporal correlation context for the previously calculated tcorr on 'filename'

ptcorr (Print Temporal Exec Correlation) will put tcorr results in their appropriate context to simplify detecting relevant / irrelevant findings.
Note that ptcorr feeds on the data calculated by the last tcorr execution and thus has to be executed after it.
You don't _have_ to specify the same filename as the one used in the tcorr execution if you want to highlight something else but the dataset is that of the tcorr exeution (read that twice if it doesn't make sense)

``` bash
./AppCompatProcessor.py ./database.db ptcorr "toto.exe"
LastModified                                       LastUpdate  FilePath                                                                   FileName                                       Size  ExecFlag
01/19/08 07:33:18                                  N/A         C:\Windows\system32                                                        net.exe                                        N/A   True
01/19/08 11:24:19                                  N/A         C:\Windows\system32                                                        cluster.exe                                    N/A   True
07/11/13 19:42:52                                  N/A         C:\$Recycle.Bin                                                            tito.tmp_                                       N/A   True
07/05/12 13:23:50                                  N/A         C:\Windows\TEMP\RarSFX0                                                    toto.exe_                                       N/A   True
07/18/15 08:57:12                                  N/A         c:\windows                                                                 setup.exe_                                     N/A   True
11/02/06 09:45:04                                  N/A         C:\Windows\system32                                                        efsui.exe                                      N/A   True
05/04/05 06:45:26                                  N/A         e:\7d5304f1a586a9b570ae6e899177\UPDATE                                     update.exe                                     N/A   True
```

**tstomp**

Time Stomp will find appcompat entries outside of Windows\[System|SysWOW64] with last modification dates matching a list of time stamp copying 'targets'.

``` bash
./AppCompatProcessor.py ./test-tstomp.db tstomp
Timestomping candidates for RedactedHost1
RowID                  RowNumber  LastModified       LastUpdate  FilePath                                                                   FileName            Size  ExecFlag
207753                 64         07/14/09 01:39:46  N/A         C:\Windows\system32                                                        svchost.exe         N/A   True
207965                 276        07/14/09 01:39:46  N/A         C:\Windows\TEMP                                                            BadFlashPlayer.exe  N/A   True

Timestomping candidates for RedactedHost2
RowID                  RowNumber  LastModified       LastUpdate  FilePath                                                                   FileName            Size  ExecFlag
163774                 63         07/14/09 01:39:46  N/A         C:\Windows\system32                                                        svchost.exe         N/A   True
164230                 519        07/14/09 01:39:46  N/A         C:\Windows\winsxs\amd64_microsoft-windows-stickynotes-app_31bf3856ad36...  StikyNot.exe        N/A   False
```
> StikyNot.exe above is a false positive.

> Tsomp will also report AmCache entries with 0 microseconds.

> Note that tsomp appears to hit pretty solidly on parsing errors from ShimCacheParser (maybe dates are duped as a result), you'll notice these as having usually truncated filepaths.

**reconscan**: Calculate recon activity in the database

All occurrences of any of the recon filenames stored in ./reconFiles.txt are located and the temporal execution distance within them used to create potential reconnaissance sessions.
A reconnaissance scoring is later calculated aggregating all recon sessions per host using an exponentially decreasing wight based on temporal execution distance just like with the tcorr module.
Recon scoring is stored in the database and can be retrieved using the 'list' module.

> Disclamer: Attackers dependent on system tools to perform reconnaissance and very methodical about it are the best for this kind of analysis, you'll probably have varying degrees of success with this module depending on the attacker's TTP.

**fevil**: Use temporal correlation on recon sessions to find potential evil [**experimental not worth your time yet**]

"Find Evil" is an experiment at zero-knowledge automatic attacker detection based on temporal execution correlation around reconnaissance sessions detected.
It's still work in progress, not really worth testing it out yet. That being said, it's been known to actually work and find evil on it's own on at least two investigations so far.

**leven \[file_name\] \[-d distance\]**: Find file naming deviations (svch0st.exe, lssas.exe, etc)

By default the 'leven' module will highlight files which present a Levenshtein distance of 1 against any of the pre-loaded legitimate filenames that exist in Windows\System32.
Pre-loaded filenames are currently limited to a default installation of Windows 7.
A file name can be supplied to find attacker typos or simple evasion attempts.
``` bash
./AppCompatProcessor.py ./database.db leven
Creating list of unique file names in database, hold on...
Searching for deviations.
Progress: [#########################] 100.0% Done...
ksetup.exe - 'setup.exe'
quser.exe - 'USER.EXE'
reg.exe - 'RegX.exe'
svchost.exe - 'svchost.exe'
winrs.exe - 'wins.exe'
```
> The optional -d flag can be used to increase the maximum Levenshtein distance reported.

**stack 'what' 'from'**: Simple but extremely powerful stacking module

'what' sql snippet, the fields you want to stack. 'from' sql snippet, what to stack (defaults to all entries). Not a great explanation but it should be obvious from the examples here.
It's really just a lazy-man's interface to direct SQL queries at the moment but it turns out to be great as it is.
``` bash
# Fishing expedition in System32:
./AppCompatProcessor.py ./database.db stack "FileName" "FilePath LIKE '%System32'"
Count  What
1      AcuInstall.exe
1      AEstSrv.exe
1      AexNSC.exe
1      appverif.exe
1      Aurora.scr
1      AutoWorkplace.exe
1      backgroundTaskHost.exe
...

# More creative fishing expedition (you have the full sqlite language power here):
./AppCompatProcessor.py ./database.db stack "FileName" "FilePath LIKE '%System32' AND length(FileName) < 8"
Count  What
1      hha.dll
1      p.exe
2      atl.dll
2      msi.dll
3      vds.exe
6      MRT.exe
...

# Check what paths we have svchost.exe in:
./AppCompatProcessor.py ./database.db stack "FilePath" "FileName = 'svchost.exe'"
Count  What
2      C:\$Recycle.Bin
12     C:\windows\SysWOW64
2446   C:\windows\system32

# Check how all those svchost.exe in System32 stack like:
./AppCompatProcessor.py ./database.db stack "FileName,LastModified,Size" "FileName = 'svchost.exe' AND FilePath LIKE '%Windows\\System32'"
Count  What         -                    -
1      svchost.exe  2010-06-02 10:06:42  13312
1      svchost.exe  2012-10-13 04:52:10  N/A
3      svchost.exe  2014-11-22 01:44:16  N/A
44     svchost.exe  2012-10-18 18:02:18  N/A
46     svchost.exe  2009-07-14 01:39:46  N/A
166    svchost.exe  2009-07-14 01:14:41  N/A
2185   svchost.exe  2012-10-18 17:40:06  N/A

# Same concept but with amcache data:
./AppCompatProcessor.py ./database.db stack "FileName,Modified2,Sha1" "FileName = 'svchost.exe' AND FilePath LIKE '%Windows\\System32'"
Count  What         -                           -
1      svchost.exe  2009-07-14 01:14:41.956099  4af001b3c3816b860660cf2de2c0fd3c1dfb4878
1      svchost.exe  2009-07-14 01:39:46.505304  619652b42afe5fb0e3719d7aeda7a5494ab193e8
2      svchost.exe  2015-07-10 04:40:18.809418  547ae8443b7ba206b3e47b1e6b02672eb4e6a5d6
2      svchost.exe  2015-07-10 10:59:58.603359  547ae8443b7ba206b3e47b1e6b02672eb4e6a5d6
8      svchost.exe  2015-10-30 07:17:49.021206  800a4c2e524fc392c45748eae1691fa01d24ea4c
10     svchost.exe  2013-08-22 12:45:17.901272  4eea9bdfe0eb41759d96ec9bd224c4519314a8fa
```
> Results are sorted per count first and then by all the fields present in the 'what' argument.

**tstack 'start_date' 'end_date' \['from'\]**: Perform time based file name stacking based on date range provided (Experimental)

tstack counts the number of executions of every file name both in and out of the supplied date range.
Results are sorted based on the ratio between both counts which theoretically should push attacker tools to the top of the list.
Optional 'from' argument: sql snippet, what to stack (defaults to all entries)
The level of noise is still too big for this module unless you use a very small time frame of activity, further refinements are being tested to improve the signal to noise ratio.

``` bash
# Time stack System32 between 2016-01-01 and 2016-04-01:
./AppCompatProcessor.py ./database.db tstack 2016-01-01 2016-04-01 "FilePath LIKE '%System32'"
Starting Time Stacker
FullPath      Hits In  Hits Out  Ratio
lssas.exe     5        0         50.00
wuauclt.exe   8        176       0.045
ie4uinit.exe  4        116       0.034
wuapp.exe     4        116       0.034
```



### AppCompatSecrets

So you thought you knew everything about AppCompat right? "Entries are sorted in order of execution bottom to top"? Wrong.

If you dig deeper and check the IR book (third edition) by Kevin Mandia then you'll find this:

``` bash
"_The output of ShimCache preserves the original order of entries in the cache meaning that rows are presented in order from most recently added or updated files to least recently added or updated. Although there is no formal documentation covering which activities result in updates to a file's shimache entry we've observed that both file execution and file creation have this effect._"
```
Now the above was not enough to explain why some of my test-sets for AppCompatProcessor didn't work as expected so I dug a little bit deeper and found out that simply opening a folder in Explorer would trigger a shimcache file entry refresh for files in the folder. But hey, there's more! Only the files who's icons are visible in the explorer window (depending on it's size) will get their shimcache entry refreshed. Even if you only get to see a hair's breadth of the icon that's enough to refresh the entry.

The resulting effect is that all the files "seen" by explorer will bubble up in your AppCompat data and will be shown in consecutive lines, the original execution order information will be lost as the new order will depend on the Explorer sorting criteria.

It's actually a tiny bit more convoluted than that even. Is you open in explorer a folder full of PE's it will default to alphabetical order (unless you've changed that) now if you then re-sort by size for example what you'll get in you appcompat data will be the files sorted by size (only those that fit into the window size) but you may be missing some.. which? you'll be missing any files that had previously had their appcompat data refreshed when you initially opened the folder so those that alphabetically fit into the explorer's window size. So there's something going on there under the hood preventing this "refresh" mechanism from kicking in again.

Why is that important? For starters you may not want the customer to grab a file and send it to you as you now know that Explorer will destroy your AppCompat data. You'll also be fooled by AppCompat if you stumble across an attacker using Explorer (weird) but actually more important than that, you now know a little bit more about how that really works which is always interesting.

Note: The same behaviour I just described seems to happen to AmCache but we get millisecond resolution timestamps there in the registry last modification timestamp (known as FirstRun in the AmCache context) so we can distinguish when stuff was executed and when we have a massive entry refresh as a result of Explorer opening our folder. BTW, that also means that what's currently known as "FirstRun" in AmCache is likely _not_ FirstRun at all according to some of my testing. We clearly need a lot more research into this artifact.
