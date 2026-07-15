import logging
import requests
import urllib 
import csv
import numpy as np
import pandas as pd
from urllib.parse import quote
from fhirpathpy import evaluate
import os
import json
from helpers import init,path_exists

baseurl="https://r4.ontoserver.csiro.au/fhir"
#baseurl="http://localhost:8080/fhir"
system="http://snomed.info/sct"
logger = logging.getLogger(__name__)        

## Checkserver is up
def check_terminology_server():
  query = "{0}/metadata".format(baseurl)
  headers = {'Accept': 'application/fhir+json'}  
  response = requests.get(query, headers=headers)
  data = response.json()
  if data["status"] != "active":
    return False
  else:
    return True



## Check for the existance of the file paths and return those in an array
def create_filepath(s2sfile,outdir):
    if (not path_exists(s2sfile)) or (not path_exists(outdir)):       
        return {}    
    filepath = {
        "s2sfile": s2sfile,
        "rrsfile": os.path.join(outdir,"rrs.txt")       
    }    
    return filepath


# match_property_name
# SNOMED Relationship qualifiers for radiology procedures
# return values:
#    0 == Procedure/modality/service
#    1 == Site 
#    2 == Laterality    
#    3 == Using Contrast
# return -1 if no match
def match_property_name(sct_code):
  index=-1
  property_list = [("260686004",0),("405813007",1),("272741003",2),("424361007",3)]
  for concept, field in property_list:
      if concept == sct_code:
        index=field
        break
  return index  


## get_valueset
## Generic Valueset getter, pass in a URL expression
## return a json response from the curl call
def get_valueset(expr):
    vsexp = baseurl + '/ValueSet/$expand?url='
    query = vsexp + quote(expr, safe='')
    headers = {'Accept': 'application/fhir+json'}
    response = requests.get(query, headers=headers)
    data = response.json()
    return data

## get_concept_all_props
## Perform a CodeSystem lookup and get all properties 
## return a json resposne from the curl call
def get_concept_all_props(code):
  cslookup='/CodeSystem/$lookup'  
  query=baseurl+cslookup+'?system='+urllib.parse.quote(system,safe='')+"&code="+code+"&property=*"
  headers = {'Accept': 'application/fhir+json'}  
  response = requests.get(query, headers=headers)
  data = response.json()
  return data


##
## read procedures
## read procedures concept (code and display) from a csv into an array
def read_focus_procedures():
  file_path = os.path.join('.','procedures.txt')
  data = []
  if not path_exists(file_path):
    print(f'Fatal error: Procedures file {file_path} does not exist.')
    return None
  with open(file_path, 'r') as file:
      reader = csv.reader(file)
      for row in reader:
          if row and row[0].startswith('#'):
              continue
          code, description = row
          data.append((code, description))
  return data


##
## read bodysite valueset id
## read bodysite valueset name, valueset ids from csv keyed by ValueSet name into a dict
def read_bodysite_vs_ids():
  file_path = os.path.join('.','body_site_vs_id.txt')
  data = {}
  if not path_exists(file_path):
    print(f'Fatal error: Procedures file {file_path} does not exist.')
    return None
  with open(file_path, 'r') as file:
      reader = csv.reader(file)
      for row in reader:
          if row and row[0].startswith('#'):
              continue
          name, id = row
          data[name] = id
  return data


## procedure mapper 
## given a procedure code (proc), lookup the ancestors to see what the base procedure is
## Get the ancestors and check to see if the match our list of common services/procedures/modalities
def procedure_mapper(proc,map):
  target = proc
  ecl='http://snomed.info/sct?fhir_vs=ecl/>'+ proc
  data = get_valueset(ecl)
  concepts = evaluate(data,"expansion.contains.code")

  if map != None:  
    for src,desc in map:          
      if src in concepts:
        target=src
        break    
  return target


##  get_body_structures
##  Get SNOMED Body Structure array, passing in a laterality
##   return an array of SNOMED concept ids for lateralised Body Structures
def get_body_structures(laterality_name):
  bodystruct_id="123037004"
  laterality_qualifier_id="272741003"
  # default to left
  laterality_id="7771000"
  if laterality_name not in ['left','right']:
    print("Error: Laterality name must be left or right")
    return {}
  else:
    if laterality_name == "right":
      laterality_id="24028007"
  ecl='http://snomed.info/sct?fhir_vs=ecl/<'+bodystruct_id+':'+laterality_qualifier_id+'='+laterality_id
  data = get_valueset(ecl)
  body_structures = evaluate(data,"expansion.contains.code")    
  return body_structures

##  get_bilateral_procedures
##  Use an ECL expression to get all bilateral procedures
##   return an array of SNOMED concept ids for bilateral Procedures
def get_bilateral_procedures():
  ecl="< 71388002 : 405813007 = (*: 272741003= (24028007)), 405813007 = (*: 272741003= (7771000))"
  ecl_url='http://snomed.info/sct?fhir_vs=ecl/'+ecl
  data = get_valueset(ecl_url)
  bilateral = evaluate(data,"expansion.contains.code")
  return bilateral



##  get_procedures_without_contrast
##  Use an ECL expression to get all `without contrast` procedures
##   return an array of SNOMED concept ids for Procedures 'without contrast'
def get_procedures_without_contrast():
  ecl='< 71388002 {{ term = "without contrast" }}'
  ecl_url='http://snomed.info/sct?fhir_vs=ecl/'+ecl
  data = get_valueset(ecl_url)
  procs = evaluate(data,"expansion.contains.code")
  return procs


## get_snomed_props
## Expand the defining relationships (properties) of the SNOMED CT Concept
##   return a pandas data frame with the expanded properties 
def get_snomed_props(code):
  # Expand the properties for the SNOMED CT concept (code)
  data=get_concept_all_props(code)
  # Evaluate a fhirpath expression to get the Concept subproperties
  expr="Parameters.parameter.where(name=\'property\').part.where(name=\'subproperty\').part"
  parts = evaluate(data,expr)
  # Iterate through the subproperty parts to find the attribute values pairs (defining relationships)
  temp_list = []
  for elem in parts:    
    if elem["name"]=="code":
      qualifier = elem["valueCode"]
      # identify what type of qualifier property e.g. method / site / Using contrast this is returning type_id (int) 0..3
      type_id = match_property_name(qualifier)
    if elem["name"] == "value":
      target_value=elem["valueCode"]
      row = [code, type_id, qualifier, target_value]
      temp_list.append(row)
  df = pd.DataFrame(temp_list,columns=["Concept","TypeId","Qualifier","TargetValue"])
  return df


## split_site
##   return the de-lateralised concept (find the proximal primitive parent)
def split_site(code):
  ecl='http://snomed.info/sct?fhir_vs=ecl/>! '+code+' {{ C definitionStatus = primitive }}'
  data = get_valueset(ecl)
  body_structure = evaluate(data,"expansion.contains.code")    
  return body_structure


## Separate lateralised body site into a body site column and a flag for left, right, both
##  left_list and right_list are arrays of concepts that have the laterality listed in the name of that variable.
def expand_body_site(df,left_list,right_list,focus_proc_list,fh):
  sep="\t"
  pre_co=""
  procedure=""
  lat=""
  contrast=""
  site=""
  sorted_props = df.sort_values(by=['TypeId'])
  for index, row in sorted_props.iterrows():
    # Procedure / Modality
    if row["TypeId"] == 0:
      if pre_co == "":
        pre_co = row["Concept"]
    # Body Site    
    if row["TypeId"] == 1:    
      concept = row["TargetValue"]
      # Extract the laterality, rule is it's bilateral if in both left and right sets.    
      if (concept in left_list):
        lat="7771000"
      elif (concept in right_list):
        lat="24028007"
      # If laterality exists, find the proximal primitive parent    
      site=row["TargetValue"]  
      if lat != "":  
         site_array=split_site(concept)
         if site_array:
            site=site_array[0]  
    # Contrast = yes
    if row["TypeId"] == 3:
      contrast="373066001"
  # Fix any bilateral procedure lateralities
  bilateral_procs = get_bilateral_procedures()
  if pre_co in bilateral_procs:
    lat="51440002"
  # Get focus procedure code for the pre-coordinated concept
  procedure = procedure_mapper(pre_co,focus_proc_list)
  # Check for procedures stating no contrast
  procs_without_contrast = get_procedures_without_contrast()
  if pre_co in procs_without_contrast:
    contrast="373067005"
  if procedure==pre_co:
    print("ERROR: Unable to determine base radiological procedure for code: "+pre_co)
  else:
   fh.write("%s%s%s%s%s%s%s%s%s\n" % (
        pre_co.strip(),
        sep,
        procedure.strip(),
        sep,
        site.strip(),
        sep,
        lat.strip(),
        sep,
        contrast.strip()
    )
)

"""
Mainline
"""

def run_main(s2sfile,outdir):
  sep="\t"
  if not check_terminology_server():
    msg="Cannot continue as {0} appears to be down. 😭".format(baseurl)
    logger.error(msg)
    print(msg)
    exit
  
  # Get Left sided body structures
  logger.info(f'Get Left sided Body Structures')
  left_list=get_body_structures("left")
  # Get Right sided body structures
  logger.info(f'Get Right sided Body Structures')
  right_list=get_body_structures("right")
  # Get list of focus procedures
  logger.info(f'Get focus procedures')   
  focus_procedures=read_focus_procedures()  


       

