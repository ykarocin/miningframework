# This script receives as input the path to a framework input file, the path to a directory generated by the miningframework and a github acess token, it downloads the release files (original and transformed versions with all project dependencies) from github and moves the files to the directory passed as input.


import sys
import requests
import json
import subprocess
import time
import shutil
import os
import csv

PATH = "path"
NAME = "name"
RESULT = "result"
GITHUB_API= "https://api.github.com"
TRAVIS_API = "https://api.travis-ci.org"
LOGIN = "login"
DOWNLOAD_URL='browser_download_url'
ASSETS="assets"
MESSAGE_PREFIX="Trigger build #"
RELEASE_PREFIX_ORIGINAL= "fetchjar-original"
RELEASE_PREFIX_TRANSFORMED= "fetchjar-transformed"
ORIGINAL_VERSION="original"
TRANSFORMED_VERSION="transformed"
jars_build_commits = {}

inputPath = sys.argv[1] # input path passed as cli argument
outputPath = sys.argv[2] # output path passed as cli argument
token = sys.argv[3] # token passed as cli argument

def fetchJars(inputPath, outputPath, token):
    # this method reads a csv input file, with the projects name and path
    # for each project it downloads the build generated via github releases
    # and moves the builds to the output generated by the framework
    
    print("Starting build collection")

    tokenUser = get_github_user(token)[LOGIN]
    parsedInput = read_input(inputPath)
    parsedOutput = read_output(outputPath)
    resultsForMerge = organize_merge_and_commits(outputPath)
    newResultsFile = []

    for project in parsedInput:

        splitedProjectPath = project[PATH].split('/')
        projectName = splitedProjectPath[len(splitedProjectPath) - 1]
        githubProject = tokenUser + '/' + projectName
        print (projectName)        

        releases = get_github_releases(token, githubProject)
        version_options = [RELEASE_PREFIX_ORIGINAL, RELEASE_PREFIX_TRANSFORMED]
        for version_option in version_options:
            # download the releases for the project moving them to the output directories
            for release in releases:
                # check if release was generated by the framework
                try:
                    if (release[NAME].startswith(version_option)): #RELEASE_PREFIX_ORIGINAL) or release[NAME].startswith(RELEASE_PREFIX_TRANSFORMED)):
                        commitSHA = release[NAME].replace(version_option,'').replace('-','') #RELEASE_PREFIX_ORIGINAL, '').replace(RELEASE_PREFIX_TRANSFORMED, '').replace('-','')
                        related_merge = ""
                        
                        if (release[NAME].startswith(RELEASE_PREFIX_ORIGINAL)):
                            related_merge = check_for_commit_jar_download_on_version_directory(resultsForMerge, commitSHA, ORIGINAL_VERSION)
                        elif (release[NAME].startswith(RELEASE_PREFIX_TRANSFORMED)):
                            related_merge = check_for_commit_jar_download_on_version_directory(resultsForMerge, commitSHA, TRANSFORMED_VERSION)
                        
                        if (related_merge != ""):
                            print ("Downloading " + commitSHA )
                            try:
                                downloadPath = mount_download_path(outputPath, projectName, related_merge   )
                                print("Download Path - " + downloadPath + " \n")
                                downloadUrl = release[ASSETS][0][DOWNLOAD_URL]
                                download_file(downloadUrl, downloadPath, commitSHA, version_option)
                                #jars_build_commits[commitSHA+""+version_option] = downloadPath
                                if (commitSHA in parsedOutput):
                                    newResultsFile.append(parsedOutput[commitSHA])
                                    untar_and_remove_file(downloadPath)
                                print (downloadPath + ' is ready')
                            except Exception as e: 
                                print(e)
                except Exception as e: 
                    print(e)

    try:
        with open(outputPath + "/data/results-with-builds.csv", 'w') as outputFile:
            outputFile.write("project;merge commit;className;method;left modifications;left deletions;right modifications;right deletions\n")
            outputFile.write("\n".join(newResultsFile))
            outputFile.close()

        output_for_semantic_conflict_study(outputPath, jars_build_commits)
    except Exception as e:
        print(e)

def output_for_semantic_conflict_study(outputPath, jars_build_commits):
    new_output = ""
    with open(outputPath+"/data/results.csv", 'r') as file:
        reader = csv.reader(file)
        count = False
        for row in reader:
            if (count != False):
                values = row[0].split(";")
                new_output += get_jar_file_location_by_version(jars_build_commits, values, RELEASE_PREFIX_ORIGINAL)
                new_output += get_jar_file_location_by_version(jars_build_commits, values, RELEASE_PREFIX_TRANSFORMED)
            count = True
    create_final_output_file(outputPath, new_output)  

def get_jar_file_location_by_version(jars_build_commits, values, version):
    path_merge_jar = find_project_jar_for_SHA(jars_build_commits, values, 1, version)
    path_left_jar = find_project_jar_for_SHA(jars_build_commits, values, 2, version)
    path_right_jar =  find_project_jar_for_SHA(jars_build_commits, values, 3, version)
    path_base_jar =  find_project_jar_for_SHA(jars_build_commits, values, 4, version)
    return format_output(values, path_merge_jar, path_left_jar, path_right_jar, path_base_jar)  

def create_final_output_file(outputPath , contents):
    with open(outputPath + "/data/results_semantic_study.csv", 'w') as outputFile:
        outputFile.write(contents)
        outputFile.close() 

def format_output(values, merge, left, right, base):
    jars_available = "false"
    if (merge != "" and base != "" and (left != "" or right != "")):
        jars_available = "true"
    return values[0]+";"+jars_available+";"+values[1]+";"+values[2]+";"+values[3]+";"+values[4]+";"+values[5]+";"+values[6].replace("|",",")+";"+base+";"+left+";"+right+";"+merge+"\n"

def find_project_jar_for_SHA(jars_build_commits, values, point, version):
    local_path = os.getcwd()+"/"
    path_jar = ""
    try:
        general_path = jars_build_commits[values[point]+"-"+version]
        for root, dirs, files in os.walk(general_path[:-13]):
            for file in files:
                if file.endswith(".jar"):
                    path_jar += local_path + os.path.join(root, file).replace("\n","")+":"
    except Exception as e:
        print(e)    
    return path_jar

def read_output(outputPath):
    try:
        fo = open(outputPath + "/data/results.csv")
        file = fo.read()
        fo.close()

        fileOutLines = file.split("\n")
        return parse_output(fileOutLines)
    except Exception as e:
        print(e)

def organize_merge_and_commits(outputPath):
    try:
        fo = open(outputPath + "/data/results.csv")
        file = fo.read()
        fo.close()

        fileOutLines = file.split("\n")
        return parse_output_merge_and_commits(fileOutLines)
    except Exception as e:
        print(e)

def parse_output(lines):
    result = {}
    for line in lines[1:]:
        cells = line.split(";")
        if (len (cells) > 1):
            result[cells[1]] = line
    return result

def parse_output_merge_and_commits(lines):
    result = {}
    for line in lines[1:]:
        cells = line.split(";")
        if (len (cells) > 1):
            result[cells[1]] = [cells[2], cells[3], cells[4]]
    return result

def check_for_commit_jar_download_on_version_directory(listMerges, commit, version):
    for oneMergeKey in listMerges:
        if (commit[:7] == oneMergeKey[:7]):
            return oneMergeKey+"/"+version+"/merge"
        elif (commit[:7] == listMerges[oneMergeKey][0][:7]):
            return oneMergeKey+"/"+version+"/left"
        elif (commit[:7] == listMerges[oneMergeKey][1][:7]):
            return oneMergeKey+"/"+version+"/right"
        elif(commit[:7] == listMerges[oneMergeKey][2][:7]):
            return oneMergeKey+"/"+version+"/base"
    return ""

def read_input(inputPath):
    f = open(inputPath, "r")
    file = f.read()
    f.close()

    bruteLines = file.split("\n")
    return parse_input(bruteLines)

def parse_input(lines):
    # parse framework input csv file 
    result = []
    for line in lines[1:]:
        cells = line.split(",")
        if (len (cells) > 1):
            method = {}
            method[NAME] = cells[0]
            method[PATH] = cells[1]
            result.append(method)
    return result

def download_file(url, target_path, commitSHA, version):
    # download file from url
    if (check_if_directory_has_jar_files(target_path)):
        jars_build_commits[commitSHA+"-"+version] = target_path
    else:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            try:
                save_jar_commit_directory(target_path, response)
                jars_build_commits[commitSHA+"-"+version] = target_path
            except Exception as e: 
                create_directory(target_path)        
                save_jar_commit_directory(target_path, response)
                untar_and_remove_file(target_path)
                jars_build_commits[commitSHA+"-"+version] = target_path

def check_if_directory_has_jar_files(target_path):
    default_path = os.getcwd()+"/"+target_path.replace("result.tar.gz","")
    for root, dirs, files in os.walk(default_path):
        for file in files:
            if file.endswith(".jar"):
                print("The jar files are already available from a previous study execution. No new download will be performed.")
                return True
    
    return False

def save_jar_commit_directory(target_path, response):
    with open(target_path, 'wb') as f:
        f.write(response.raw.read())        

def create_directory(target_path):
    target = target_path.split("/result.tar.gz")[0]
    os.mkdir(target)

def mount_download_path(outputPath, project_name, commitSHA):
    # mount path where the downloaded build will be moved to
    return outputPath + '/files/' + project_name + '/' + commitSHA + '/result.tar.gz'

def untar_and_remove_file(downloadPath): 
    downloadDir = downloadPath.replace('result.tar.gz', '')
    subprocess.call(['mkdir', downloadDir + 'build'])
    subprocess.call(['tar', '-xf', downloadPath, '-C', downloadDir])
    subprocess.call(['rm', downloadPath])


def get_travis_project_builds(project):
    return requests.get(TRAVIS_API + '/repos/' + project).json()

def get_github_user(token):
    return requests.get(GITHUB_API + '/user', headers=get_headers(token)).json()

def get_github_releases(token, project):
    res = requests.get(GITHUB_API + '/repos/' + project + '/releases', headers=get_headers(token))
    page = 1
    reqRes = get_github_releases_page(token, project, page)
    result = reqRes
    # this is a workaround to get all releases at once, it is needed because of the API pagination
    while len(reqRes):
        page += 1
        reqRes = get_github_releases_page(token, project, page)
        result = result + reqRes
    return result

def get_github_releases_page(token, project, page_number):
    res = requests.get(GITHUB_API + '/repos/' + project + '/releases?page=' + str(page_number),headers=get_headers(token))
    try:
        res.raise_for_status()

        return res.json()
    except Exception as e:
        raise Exception("Error getting github releases: " + str(e))

def get_headers(token):
    return {
        "Authorization": "token " + token
    }


def remove_commit_files_without_builds (outputPath, projectName):
    files_path = outputPath + "/files/" + projectName +  "/"

    if (os.path.exists(files_path)): 
        commit_dirs = os.listdir(files_path)

        for directory in commit_dirs:
            commit_dir = files_path + directory
            build_dir = commit_dir

            if (not os.path.exists(build_dir)):
                shutil.rmtree(commit_dir)

        if (len (os.listdir(files_path)) == 0 ):
            shutil.rmtree(files_path)

fetchJars(inputPath, outputPath, token)