import arcpy
import os.path
import sys
import math
import shutil
import glob

from GeMS_utilityFunctions import *

# September 2017: now invokes arcpy.da.Editor in line 183
# 5 October 2017: fixed crash when symbolizing CMU feature dataset
# 17 July 2019: upgraded to python 3, renamed GeMS_SetSymbols_AGP2.py

versionString = "GeMS_SetSymbols.py, version of 8/21/23"
rawurl = "https://raw.githubusercontent.com/DOI-USGS/gems-tools-pro/master/Scripts/GeMS_SetSymbols.py"
checkVersion(versionString, rawurl, "gems-tools-pro")

EightfoldLineDict = {}
TwofoldOrientPointDict = {}
MySymbolDict = {}

unrecognizedTypes = []

script_path = os.path.abspath(sys.argv[0])
script_folder = os.path.dirname(script_path)
tbx_folder = os.path.dirname(script_folder)
dictionaryFile = os.path.join(tbx_folder, "Resources", "Type-FgdcSymbol.txt")

debug1 = False


def buildSymbolDicts(dFile):
    df = open(dictionaryFile, "r")
    for aline in df:
        if aline[0] != "#":
            words = aline.split()
            if len(words) > 0:
                aline = aline[:-1]
                newWords = []
                words = aline.split("|")
                for word in words:
                    newWord = word.lstrip().rstrip()
                    newWords.append(newWord)
                if aline == "***Eight-fold Lines***":
                    aDict = EightfoldLineDict
                elif aline == "***Two-fold Orientation Points***":
                    aDict = TwofoldOrientPointDict
                elif aline == "***My Symbols***":
                    aDict = MySymbolDict
                else:
                    key = newWords[0]
                    val1 = newWords[1]
                    if len(newWords) > 2:
                        val2 = newWords[2]
                        aDict[key] = [val1, val2]
                    else:
                        aDict[key] = val1


def incrementSymbol(sym, increment):
    symWords = sym.split(".")
    lastWord = symWords[len(symWords) - 1]
    newLastWord = str(int(lastWord) + increment).zfill(len(lastWord))
    newSym = sym[0 : 0 - len(lastWord)] + newLastWord
    return newSym


def unrecognizedType(t):
    if not t in unrecognizedTypes:
        unrecognizedTypes.append(t)


def hasCartoRep(fds, fc):
    hostGdb = os.path.dirname(fds)
    domains = arcpy.da.ListDomains(hostGdb)
    shortFc = os.path.basename(fc)
    hasRep = False
    repDomain = ""
    for aDomain in domains:
        if aDomain.name.find(shortFc) > -1 and aDomain.name.find("_rep") > -1:
            hasRep = True
            repDomain = aDomain
    return hasRep, repDomain


def trimLeftZeros(fgdc):
    words = fgdc.split(".")
    fgdc1 = ""
    for word in words:
        fgdc1 = fgdc1 + "." + str(int(word))
    fgdc2 = fgdc1[1:]
    return fgdc2


def buildRepRuleDict(repDomain):
    newDict = {}
    domKeys = list(repDomain.codedValues.keys())
    domKeys.sort()
    for i in domKeys:
        newDict[repDomain.codedValues[i]] = i
    return newDict


def test_locks(gdb, n):
    match_string = os.path.join(gdb, "{}*rd.lock".format(n))
    read_locks = glob.glob(match_string)
    if read_locks:
        arcpy.AddError("Cannot process!")
        addMsgAndPrint("There is a table-view lock on {}".format(n))
        addMsgAndPrint(
            "Close it if open in ArcGIS Pro or compact the "
            "geodatabase if being run from the command line "
        )
        sys.exit(1)
    match_string = os.path.join(gdb, "{}*ed.lock".format(n))
    ed_locks = glob.glob(match_string)
    if ed_locks:
        arcpy.AddError("Cannot process!")
        addMsgAndPrint("There is an edit lock on {}".format(n))
        addMsgAndPrint(
            "Close the edit session if open in ArcGIS Pro or compact the "
            "geodatabase if being run from the command line "
        )
        sys.exit(1)


def test_topology(gdb, n):
    tops = arcpy.da.Walk(gdb, datatype="Topology")
    for top in tops:
        if top[2]:
            desc = arcpy.Describe(os.path.join(top[0], top[2][0]))
            if n in desc.featureClassNames:
                return True


#####################################################
addMsgAndPrint("  {}".format(versionString))
addMsgAndPrint("  dictionary file: {}".format(dictionaryFile))

# get inputs
inFds = sys.argv[1]
mapScale = float(sys.argv[2])
certain_Approxmm = float(sys.argv[3])
if sys.argv[4] == "true":
    useInferred = True
else:
    useInferred = False

if useInferred:
    approx_Inferredmm = float(sys.argv[5])
else:
    approx_Inferredmm = 100

if sys.argv[6] == "true":
    useApproxOrient = True
else:
    useApproxOrient = False

orientThresholdDegrees = float(sys.argv[7])

if sys.argv[8] == "true":
    setPolys = True
else:
    setPolys = False

input_schema = arcpy.GetParameterAsText(8) + '.'
input_mapname = arcpy.GetParameterAsText(9)


# set thresholds
approxThreshold = mapScale * certain_Approxmm / 1000.0
inferredThreshold = mapScale * approx_Inferredmm / 1000.0
# read dictionaryFile to build symbolDicts
buildSymbolDicts(dictionaryFile)

gdb = os.path.dirname(inFds)
arcpy.env.workspace = gdb
Fds = os.path.basename(inFds)

if getGDBType(gdb) == 'FileGDB':
    whereclause = "OBJECTID > -1"
if getGDBType(gdb) == 'EGDB':
    whereclause = "MapName = '" + input_mapname + "'" 
    
# set featureClasses  (ContactsAndFaults, OrientationPoints, GeologicLines)
caf = arcpy.ListFeatureClasses(input_schema + "ContactsAndFaults", feature_dataset=Fds)[0]
caf = os.path.join(inFds, caf)
if inFds.find("CorrelationOfMapUnits") == -1:
    gel = caf.replace("ContactsAndFaults", "GeologicLines")
    orp = caf.replace("ContactsAndFaults", "OrientationPoints")
    mup = caf.replace("ContactsAndFaults", "MapUnitPolys")
    fields = [
        "Type",
        "IsConcealed",
        "LocationConfidenceMeters",
        "ExistenceConfidence",
        "IdentityConfidence",
        "Symbol",
        "OBJECTID",
    ]
else:  # is CMU
    caf = ""
    mup = os.path.join(inFds, "CMUMapUnitPolys")
    gel = ""
    orp = ""
    fields = ["Type"]
dmu = os.path.join(os.path.dirname(inFds), "DescriptionOfMapUnits")

# addMsgAndPrint('  Feature dataset {}, can be locked = {}'.format(inFds, arcpy.TestSchemaLock(inFds)))
top_bool = True
for fc in caf, gel:
    if arcpy.Exists(fc):
        if numberOfRows(fc) > 0:
            addMsgAndPrint("  processing {}".format(os.path.basename(fc)))
        if debug:
            addMsgAndPrint("fields = {}".format(fields))

        hasRep, repDomain = hasCartoRep(inFds, fc)
        if hasRep:
            fields.append("RuleID1")
            repRuleDict = buildRepRuleDict(repDomain)

        # if there are table-view or edit locks on the layer,
        # the updatecursor will fail, so check now and end if necessary
        test_locks(gdb, os.path.basename(fc))

        edit = arcpy.da.Editor(gdb)
        if getGDBType(gdb) == 'FileGDB':
            edit.startEditing(False, False)
        if getGDBType(gdb) == 'EGDB':
            edit.startEditing(False, True)

        with arcpy.da.UpdateCursor(fc, fields, where_clause = whereclause) as cursor:
            for row in cursor:
                rowChanged = False
                typ = row[0]
                isCon = row[1]
                locConfM = row[2]
                exConf = row[3]
                idConf = row[4]
                sym = row[5]
                if debug1:
                    addMsgAndPrint(typ)

                if typ in list(EightfoldLineDict.keys()):
                    if debug1:
                        addMsgAndPrint("{} is in EightfoldLineDict".format(typ))
                    inc = 0
                    if isQuestionable(exConf) or isQuestionable(idConf):
                        inc = inc + 1
                    if isCon.lower() == "n":
                        if useInferred and locConfM > inferredThreshold:
                            inc = inc + 4
                        elif locConfM > approxThreshold:
                            inc = inc + 2
                    else:  # isCon == 'Y'
                        inc = inc + 6
                    row[5] = incrementSymbol(EightfoldLineDict[typ], inc)
                    if row[5] != sym:
                        rowChanged = True
                elif typ in list(MySymbolDict.keys()):
                    row[5] = MySymbolDict[typ]
                    if row[5] != sym:
                        rowChanged = True
                else:
                    unrecognizedType(typ)

                if rowChanged:
                    # arcpy.AddMessage('{}: {} : {}'.format(row[6], sym, row[5]))
                    if hasRep:
                        # turn GSC label into original FGDC label: 06.03 to 6.3
                        noZeros = trimLeftZeros(row[5])
                        if repRuleDict.has_key(noZeros):
                            row[6] = repRuleDict[noZeros]
                    if top_bool:
                        edit.startOperation()
                    cursor.updateRow(row)
                    if top_bool:
                        edit.stopOperation()

        if top_bool:
            edit.stopEditing(True)
        if top_bool:
            del edit

fields = ["Type", "OrientationConfidenceDegrees", "Symbol"]
fc = orp
if arcpy.Exists(fc):
    addMsgAndPrint("  processing {}".format(os.path.basename(fc)))
    hasRep, repDomain = hasCartoRep(inFds, fc)
    if hasRep:
        fields.append("RuleID1")
        repRuleDict = buildRepRuleDict(repDomain)

    # if there are table-view or edit locks on the layer,
    # the updatecursor will fail, so check now and end if necessary
    test_locks(gdb, os.path.basename(fc))

    # #featureclasses in topologies can only be editing inside
    # #edit sessions
    # top_bool = test_topology(gdb, os.path.basename(fc))
    # if top_bool:
    edit = arcpy.da.Editor(gdb)
    if getGDBType(gdb) == 'FileGDB':
        edit.startEditing(False, False)
    if getGDBType(gdb) == 'EGDB':
        edit.startEditing(False, True)
    
    if debug:
        addMsgAndPrint("fields = {},  fc = {}".format(fields, fc))

    with arcpy.da.UpdateCursor(fc, fields, whereclause) as cursor:
        for row in cursor:
            typ = row[0]
            orConf = row[1]
            rowChanged = False
            if typ in list(TwofoldOrientPointDict.keys()):
                rowChanged = True
                if orConf > orientThresholdDegrees and useApproxOrient:
                    row[2] = TwofoldOrientPointDict[typ][1]
                else:
                    row[2] = TwofoldOrientPointDict[typ][0]
            elif typ in list(MySymbolDict.keys()):
                # addMsgAndPrint('**'+typ+'**')
                rowChanged = True
                row[2] = MySymbolDict[typ]
            else:
                # addMsgAndPrint('++'+typ+'++')
                unrecognizedType(typ)
            if rowChanged:
                if hasRep:
                    # turn GSC label into original FGDC label: 06.03 to 6.3
                    noZeros = trimLeftZeros(row[2])
                    if repRuleDict.has_key(noZeros):
                        row[3] = repRuleDict[noZeros]
                if top_bool:
                    edit.startOperation()
                cursor.updateRow(row)
                if top_bool:
                    edit.stopOperation()

    if top_bool:
        edit.stopEditing(True)
    if top_bool:
        del edit

addMsgAndPrint("  \n  Unrecognized Type values: ")
if len(unrecognizedTypes) == 0:
    addMsgAndPrint("    none")
else:
    for t in unrecognizedTypes:
        if t != None:
            addMsgAndPrint("    " + t)
        else:
            addMsgAndPrint("    missing type value")
addMsgAndPrint("  ")

if setPolys:
    if arcpy.Exists(dmu) and arcpy.Exists(mup):
        addMsgAndPrint("  setting Symbol and Label values in MapUnitPolys")
        # if there are table-view or edit locks on the layer,
        # the updatecursor will fail, so check now and end if necessary
        test_locks(gdb, os.path.basename(fc))

        # #featureclasses in topologies can only be editing inside
        # #edit sessions
        # top_bool = test_topology(gdb, os.path.basename(fc))
        # if top_bool:
        edit = arcpy.da.Editor(gdb)
        if getGDBType(gdb) == 'FileGDB':
            edit.startEditing(False, False)
        if getGDBType(gdb) == 'EGDB':
            edit.startEditing(False, True)

        mupTable = "mupTable"
        testAndDelete(mupTable)
        arcpy.MakeTableView_management(mup, mupTable)
        # check to see if join already exists
        joinAdded = True
        fields = arcpy.ListFields(mupTable)
        for f in fields:
            if f.name.find("DescriptionOfMapUnits.Symbol") > -1:
                joinAdded = False
        # else add join
        if joinAdded:
            arcpy.AddJoin_management(mupTable, "MapUnit", dmu, "MapUnit")

        # get field names for Symbol, Label
        mupSymbol = os.path.basename(mup) + ".Symbol"
        mupLabel = os.path.basename(mup) + ".Label"

        # calculate Symbol
        if top_bool:
            edit.startOperation()
        arcpy.CalculateField_management(
            mupTable, mupSymbol, "!DescriptionOfMapUnits.Symbol!", "PYTHON"
        )
        if top_bool:
            edit.stopOperation()

        ## calculate Label
        if top_bool:
            edit.startOperation()
        arcpy.CalculateField_management(
            mupTable, mupLabel, "!DescriptionOfMapUnits.Label!", "PYTHON"
        )
        if top_bool:
            edit.stopOperation()
        # calculate Label for IdentityConfidence <> 'certain'
        if inFds.find("CorrelationOfMapUnits") == -1:
            selectField = arcpy.AddFieldDelimiters(
                os.path.dirname(inFds), "IdentityConfidence"
            )
            arcpy.SelectLayerByAttribute_management(
                mupTable, "NEW_SELECTION", selectField + " <> 'certain'"
            )
            if top_bool:
                edit.startOperation()
            arcpy.CalculateField_management(
                mupTable,
                "MapUnitPolys.Label",
                '!DescriptionOfMapUnits.Label! + "?"',
                "PYTHON",
            )
            if top_bool:
                edit.stopOperation()
        # if joinAdded, remove join
        if joinAdded:
            arcpy.RemoveJoin_management(mupTable)
    else:
        addMsgAndPrint("Table " + dmu + " does not exist.")

    if top_bool:
        edit.stopEditing(True)
    if top_bool:
        del edit




#-------------------validation script----------
import os
from pathlib import Path
sys.path.insert(1, os.path.join(os.path.dirname(__file__),'Scripts'))
from GeMS_utilityFunctions import *
class ToolValidator:
  # Class to add custom behavior and properties to the tool and tool parameters.

    def __init__(self):
        # set self.params for use in other function
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self):
        # Customize parameter properties. 
        # This gets called when the tool is opened.
        self.params[8].enabled = False
        self.params[9].enabled = False          
        return

    def updateParameters(self):
        # Modify parameter values and properties.
        # This gets called each time a parameter is modified, before 
        # standard validation.
        gdb = os.path.dirname(self.params[0].valueAsText)
        if getGDBType(gdb) == 'EGDB':
            self.params[8].enabled = True    
            db_schema = os.path.basename(self.params[0].valueAsText).split('.')[0] + '.' + os.path.basename(self.params[0].valueAsText).split('.')[1]
            
            schemaList = []
            arcpy.env.workspace = gdb  
            datasets = arcpy.ListDatasets("*GeologicMap*", "Feature")	
            for dataset in datasets:
                schemaList.append(dataset.split('.')[0] + '.' + dataset.split('.')[1])
            self.params[8].filter.list = sorted(set(schemaList))	

            if self.params[8].value is not None and len(arcpy.ListTables(db_schema + '.Domain_MapName')) == 1:
                self.params[9].enabled = True 
                mapList = []
                for row in arcpy.da.SearchCursor(gdb + '\\' + self.params[8].value + '.Domain_MapName',['code']):
                    mapList.append(row[0])
                self.params[9].filter.list = sorted(set(mapList))  
            else:
                self.params[9].enabled = False
                self.params[9].value = None           
        else:
            self.params[8].enabled = False
            self.params[8].value = None
            self.params[9].enabled = False
            self.params[9].value = None
        return

    def updateMessages(self):
        # Customize messages for the parameters.
        # This gets called after standard validation.
        return

    # def isLicensed(self):
    #     # set tool isLicensed.
    # return True