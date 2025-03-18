# Script to step through an identified subset of feature classes in GeologicMap feature dataset
# and, for specified values of independent fields, calculate values of dependent fields.
# Useful for translating Alacarte-derived data into NCGMP09 format, and for using NCGMP09
# to digitize data in Alacarte mode.
#
# Edited 30 May 2019 by Evan Thoms:
#   Updated to work with Python 3 in ArcGIS Pro2
#   Ran script through 2to3 to fix minor syntax issues
#   Manually edited the rest to make string building for messages
#   and whereClauses more pythonic
#   Added better handling of boolean to determine overwriting or not of existing values

usage = """
Usage: GeMS_AttributeByKeyValues.py <geodatabase> <file.txt> <force calculation>
  <geodatabase> is an NCGMP09-style geodatabase--with mapdata in feature
     dataset GeologicMap
  <file.txt> is a formatted text file that specifies feature classes,
     field names, values of independent fields, and values of dependent fields.
     See Dig24K_KeyValues.txt for an example and format instructions.
  <force calculation> boolean (True/False with or without quotes) that will 
     determine if existing values may be overwritten (True) or only null, 0, orgot
     otherwise empty values will be calculated (False)
     """
import arcpy, sys
from GeMS_utilityFunctions import *

versionString = "GeMS_AttributeByKeyValues.py, version of 8/21/23"
rawurl = "https://raw.githubusercontent.com/DOI-USGS/gems-tools-pro/master/Scripts/GeMS_AttributeByKeyValues.py"
checkVersion(versionString, rawurl, "gems-tools-pro")

separator = "|"


def makeFieldTypeDict(fds, fc):
    fdict = {}
    fields = arcpy.ListFields(fds + "/" + fc)
    for fld in fields:
        fdict[fld.name] = fld.type
    return fdict


addMsgAndPrint("  " + versionString)

# if len(sys.argv) != 4:
    # addMsgAndPrint(usage)
    # sys.exit()

gdb = arcpy.GetParameterAsText(0)
keylines1 = open(arcpy.GetParameterAsText(1), "r").readlines()
if arcpy.GetParameterAsText(2).lower() == "true":
    forceCalc = True
else:
    forceCalc = False

if forceCalc:
    addMsgAndPrint("Forcing the overwriting of existing values")

arcpy.env.workspace = gdb
if getGDBType(gdb) == 'EGDB':
    dbschema = arcpy.GetParameterAsText(3) + '.'
    dbschemafilter = dbschema + '*'
    #dbschemawhere = "MapName = '" + arcpy.GetParameterAsText(4) + "'"
    arcpy.env.workspace = dbschema + "GeologicMap"
elif getGDBType(gdb) == 'FileGDB':    
    dbschema= ''
    dbschemafilter = '*'
    arcpy.env.workspace = "GeologicMap"

featureClasses = arcpy.ListFeatureClasses(dbschemafilter)
arcpy.AddMessage(featureClasses)
arcpy.env.workspace = gdb

# remove empty lines from keylines1
keylines = []
for lin in keylines1:
    lin = lin.strip()
    if len(lin) > 1 and lin[0:1] != "#":
        keylines.append(lin)
arcpy.AddMessage(keylines)

countPerLines = []
for line in keylines:
    countPerLines.append(len(line.split(separator)))
arcpy.AddMessage(countPerLines)
n = 0
while n < len(keylines):
    addMsgAndPrint(n)
    arcpy.AddMessage(n)
    terms = keylines[n].split(separator)  # remove newline and split on commas
    arcpy.AddMessage(terms)
    if len(terms) == 1:
        fClass = terms[0]
        if dbschema + fClass in featureClasses:
            mFieldTypeDict = makeFieldTypeDict(dbschema + "GeologicMap", dbschema + fClass)
            n = n + 1
            mFields = keylines[n].split(separator)
            for i in range(len(mFields)):
                mFields[i] = mFields[i].strip()  # remove leading and trailing whitespace
                numMFields = len(mFields)
            addMsgAndPrint("  {}".format(dbschema + fClass))
        else:
            if len(fClass) > 0:  # catch trailing empty lines
                addMsgAndPrint("  {} not in {}/GeologicMap".format(fClass, gdb))
                while (countPerLines[n + 1] > 1):  # This advances the loop till the number of items in the terms list is again one, which is when the next feature class is considered
                    arcpy.AddMessage("loop count = " + str(n))
                    if n < len(countPerLines) - 2:
                        # arcpy.AddMessage("count per line = " + str(countPerLines[n]))
                        n = n + 1
                    elif n == len(countPerLines) - 2:
                        n = len(countPerLines)
                        break
                    else:
                        arcpy.warnings("Unexpected condition met")

    else:  # must be a key-value: dependent values line
        vals = keylines[n].split(separator)
        if len(vals) != numMFields:
            addMsgAndPrint("\nline:\n  {}\nhas wrong number of values. Exiting.".format(keylines[n]))
            sys.exit()
        for i in range(len(vals)):  # strip out quotes
            vals[i] = vals[i].replace("'", "")
            vals[i] = vals[i].replace('"', "")
            # remove leading and trailing whitespace
            vals[i] = vals[i].strip()
        # iterate through mFields 0--len(mFields)
        #  if i == 0, make table view, else resel rows with NULL values for attrib[i] and calc values
        arcpy.env.overwriteOutput = True  # so we can reuse table tempT
        for i in range(len(mFields)):
            if i == 0:  # select rows with specified independent value
                whereClause = "{} = '{}'".format(arcpy.AddFieldDelimiters(dbschema + fClass, mFields[i]), vals[0])
                if getGDBType(gdb) == 'EGDB':
                    whereClause = whereClause + " AND MapName = '" + arcpy.GetParameterAsText(4) + "'"
                arcpy.AddMessage(whereClause)
                arcpy.MakeTableView_management(dbschema + "GeologicMap/{}".format(dbschema + fClass), "tempT", whereClause)
                nSel = int(str(arcpy.GetCount_management("tempT")))  # convert from Result object to integer
                #arcpy.AddMessage("{} record(s) in TempT".format(nSel))
                if nSel == -1:
                    addMsgAndPrint("    appears to be no value named: {} in: {}".format(vals[0], mFields[0]))
                else:
                    addMsgAndPrint("    selected {} = {}, n = {}".format(mFields[0], vals[0], str(nSel)))
            else:  # reselect rows where dependent values are NULL and assign new value
                if forceCalc:
                    if nSel > 0:
                        if mFieldTypeDict[mFields[i]] == "String":
                            arcpy.CalculateField_management("tempT", mFields[i], '"{}"'.format(str(vals[i])))
                        elif mFieldTypeDict[mFields[i]] in ["Double","Single","Integer","SmallInteger",]:
                            arcpy.CalculateField_management("tempT", mFields[i], vals[i])
                        addMsgAndPrint("        calculated {} = {}".format(mFields[i], str(vals[i])))
                elif nSel > 0:
                    addMsgAndPrint("Calculating only NULL fields")
                    whereClause = "{} IS NULL".format(arcpy.AddFieldDelimiters(dbschema + fClass, mFields[i]))
                    if mFieldTypeDict[mFields[i]] == "String":
                        whereClause = "{0} OR {1} = '' OR {1} = ' '".format(whereClause, mFields[i])
                    elif mFieldTypeDict[mFields[i]] in ["Double","Single","Integer","SmallInteger",]:
                        whereClause = "{} OR {} = 0".format(whereClause, mFields[i])
                    arcpy.AddMessage(whereClause)
                    arcpy.SelectLayerByAttribute_management("tempT", "NEW_SELECTION", whereClause)
                    nResel = int(str(arcpy.GetCount_management("tempT")))  # convert result object to int
                    addMsgAndPrint("      reselected {} = NULL, blank, or 0, n = {}".format(mFields[i], (nResel)))
                    if nResel > 0:
                        if mFieldTypeDict[mFields[i]] == "String":
                            arcpy.CalculateField_management("tempT", mFields[i], '"{}"'.format(str(vals[i])))
                        elif mFieldTypeDict[mFields[i]] in ["Double","Single","Integer","SmallInteger",]:
                            arcpy.CalculateField_management("tempT", mFields[i], vals[i])
                        addMsgAndPrint("        calculated {} = {}".format(mFields[i], str(vals[i])))
    n = n + 1



#-------------------validation script----------
import os,glob
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
        self.params[3].enabled = False
        self.params[4].enabled = False
        return

    def updateParameters(self):
        # Modify parameter values and properties.
        # This gets called each time a parameter is modified, before 
        # standard validation.
        gdb = self.params[0].valueAsText
        if getGDBType(gdb) == 'EGDB':
            self.params[3].enabled = True 
            schemaList = []
            arcpy.env.workspace = gdb  
            datasets = arcpy.ListDatasets("*GeologicMap*", "Feature")	
            for dataset in datasets:
                schemaList.append(dataset.split('.')[0] + '.' + dataset.split('.')[1])
            self.params[3].filter.list = sorted(set(schemaList))	

            if self.params[3].value is not None and len(arcpy.ListTables(self.params[3].value + '.Domain_MapName')) == 1:  
                self.params[4].enabled = True 
                mapList = []
                for row in arcpy.da.SearchCursor(gdb + '\\' + self.params[3].value + '.Domain_MapName',['code']):
                    mapList.append(row[0])
                self.params[4].filter.list = sorted(set(mapList)) 
            else:
                self.params[4].enabled = False
                self.params[4].value = None
            
        else:
            self.params[3].enabled = False
            self.params[3].value = None
            self.params[4].enabled = False
            self.params[4].value = None            
            
            
        return

    def updateMessages(self):
        # Customize messages for the parameters.
        # This gets called after standard validation.
        return

    # def isLicensed(self):
    #     # set tool isLicensed.
    # return True
            