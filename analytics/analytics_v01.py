#****************************************************************
#  File: AnalyticsAPIv01.py
#
# Copyright (c) 2015, Georgia Tech Research Institute
# All rights reserved.
#
# This unpublished material is the property of the Georgia Tech
# Research Institute and is protected under copyright law.
# The methods and techniques described herein are considered
# trade secrets and/or confidential. Reproduction or distribution,
# in whole or in part, is forbidden except by the express written
# permission of the Georgia Tech Research Institute.
#****************************************************************/

from flask import Flask, request, jsonify, redirect, url_for, g, abort, send_from_directory
import markdown, json
from flask import stream_with_context, request, Response
import pymongo, sys, json, os, socket, shutil, string, re
import utils
from werkzeug import secure_filename
from flask.ext import restful
from flask.ext.restplus import Api, Resource, fields
from datetime import datetime
import subprocess
from multiprocessing import Process, Queue
# from ANALYTICS_CONSTANTS import *
from CONSTANTS import *

ALLOWED_EXTENSIONS = ['py']

app = Flask(__name__)
app.debug = True

api = Api(app, version="0.1", title="Analytics API", 
    description="Analytics-Framework API supporting creation and use of analytics (Copyright &copy 2015, Georgia Tech Research Institute)")

ns_a = api.namespace('analytics')
ns_r = api.namespace('results')



###################################################################################################


@api.model(fields={
                'created': fields.String(description='Timestamp of creation'),
                'id': fields.String(description='Unique ID for the matrix', required=True),
                'src_id': fields.String(description='Unique ID for the source used to generate the matrix', required=True),
                'mat_type': fields.String(description='Matrix type'),
                'name': fields.String(description='Matrix name'),
                'outputs': fields.List(fields.String, description='List of output files associated with the matrix', required=True),
                'rootdir': fields.String(description='Path to the associated directory', required=True),
                })
class Matrix(fields.Raw):
    def format(self, value):
        return { 
                'created': value.created,
                'id': value.id,
                'src_id': value.src_id,
                'mat_type': value.mat_type,
                'name': value.name,
                'outputs': value.outputs,
                'rootdir': value.rootdir
                }

@api.model(fields={
                'attrname': fields.String(description='Python variable name', required=True),
                'max': fields.Float(description='Max value to allow for input'),
                'min': fields.Float(description='Min value to allow for input'),
                'name': fields.String(description='Name to use for display', required=True),
                'step': fields.Float(description='Step to use for numeric values'),
                'type': fields.String(description='Kind of html input type to display', required=True),
                'value': fields.String(description='Default value to use', required=True),
                })
class AnalyticParams(fields.Raw):
    def format(self, value):
        return { 
                'attrname': value.attrname,
                'max': value.max,
                'min': value.min,
                'name': value.name,
                'step': value.step,
                'type': value.type,
                'value': value.value,
                }

api.model('Analytic', {
    'analytic_id': fields.String(description='Unique ID for the analytic', required=True),
    'classname': fields.String(description='Classname within the python file', required=True),
    'description': fields.String(description='Description for the analytic'),
    'inputs': fields.List(fields.String, description='List of input files for the analytic', required=True),
    'name': fields.String(description='Analytic name'),
    'parameters': fields.List(AnalyticParams, description='List of input parameters needed by the analytic'),
    'outputs': fields.List(fields.String, description='List of output files generated by the analytic', required=True),
    'type': fields.String(description='Type of analytic: {Dimension Reduction, Clustering, Classification, Statistics}', required=True),
})


@api.model(fields={ 
                'analytic_id': fields.String(description='Unique ID for the analytic used to generate the result', required=True),
                'created': fields.String(description='Timestamp of creation'),
                'id': fields.String(description='Unique ID for the result', required=True),
                'name': fields.String(description='Result name'),
                'parameters': fields.List(AnalyticParams, description='List of input parameters used by the analytic'),
                'ouptuts': fields.List(fields.String, description='List of output files associated with that result', required=True),
                'rootdir': fields.String(description='Path to the associated directory', required=True),
                'src_id': fields.String(description='Unique ID for the matrix used to generate the result', required=True),
                })
class Result(fields.Raw):
    def format(self, value):
        return { 
                'analytic_id': value.analytic_id,
                'created': value.created,
                'id': value.id,
                'name': value.name,
                'parameters': value.parameters,
                'ouptuts': value.outputs,
                'rootdir': value.rootdir,
                'src_id': value.src_id
                }

api.model('Results', {
    'results': fields.List(Result, description='List of results for this particular matrix', required=True),
    'rootdir': fields.String(description='Path to the associated directory', required=True),
    'src': Matrix(description='Matrix from which these results were generated'),
    'src_id': fields.String(description='Unique ID for the matrix', required=True),
})


###################################################################################################

@ns_a.route('/')
class Analytics(Resource):
    @api.doc(model='Analytic')
    def get(self):
        '''
        Returns a list of available analytics.
        All analytics registered in the system will be returned. If you believe there is an analytic that exists in the system but is not present here, it is probably not registered in the MongoDB database.
        '''
        client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
        col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
        cur = col.find()
        analytics = []
        for src in cur:
            response = {key: value for key, value in src.items() if key != '_id'}
            analytics.append(response)

        return analytics


    @api.hide
    @api.doc(responses={201: 'Success', 415: 'Unsupported filetype'})
    def put(self):
        '''
        Add a new analytic via file upload
        '''
        # analytic_id = 'alg' + utils.getNewId()
        time = datetime.now()
        # make the id more meaningful
        file = request.files['file']
        ext = re.split('\.', file.filename)[1]
        if not ext in ALLOWED_EXTENSIONS:
            return 'This filetype is not supported.', 415

        #save the file
        filename = secure_filename(file.filename)
        name = re.split('\.', filename)[0]
        analytic_id = name + str(time.year) + str(time.month) + str(time.day) + str(time.hour) + str(time.minute) + str(time.second)
        filepath = ANALYTICS_OPALS + analytic_id + '.py'
        file.save(filepath)

        #get the metadata from the file
        metadata = utils.get_metadata(analytic_id)
        metadata['analytic_id'] = analytic_id


        client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
        col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]

        col.insert(metadata)
        meta = {key: value for key, value in metadata.items() if key != '_id'}

        return meta, 201

    # @api.hide
    # @api.doc(responses={201: 'Success', 406: 'Error with analytic content'})
    # def post(self):
    #     '''
    #     Add a new analytic via form
    #     '''
    #     time = datetime.now()
    #     # make the id more meaningful
    #     data = request.get_json()

    #     #create a temp file
    #     time = datetime.now()
    #     analytic_id = data['classname'] + str(time.year) + str(time.month) + str(time.day) + str(time.hour) + str(time.minute) + str(time.second)

    #     with open(ANALYTICS_OPALS + analytic_id + '.py', 'w') as temp:
    #         temp.write('def get_classname():\n    return \'' + data['classname'] + '\'\n\n')
    #         temp.write(data['code'] + '\n\n')


    #     #test the alg with a dense matrix, show traceback, delete analytic file
    #     success = utils.test_analysis(analytic_id, TESTFILEPATH, TESTSTOREPATH)
    #     if not success:
    #             os.remove(ANALYTICS_OPALS + analytic_id + '.py')
    #             return 'Problem with provided algorithm', 406

    #     #save the file, delete results
    #     else:  
    #         for i in os.listdir(TESTSTOREPATH):
    #             os.remove(TESTSTOREPATH + i)
    #         #get the metadata from the file
    #         metadata = utils.get_metadata(analytic_id)
    #         metadata['analytic_id'] = analytic_id

    #         client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
    #         col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]

    #         col.insert(metadata)
    #         meta = {key: value for key, value in metadata.items() if key != '_id'}

    #         return meta, 201

    #     return ''

    @ns_a.route('/options/')
    class Options(Resource):
        @api.doc(body='Matrix', params={'payload': 
            '''Must be a list of the model described to the right. Try this: 
            [{
              "created": "string",
              "id": "string",
              "mat_type": "string",
              "name": "string",
              "outputs": [
                "matrix.csv"
              ],
              "rootdir": "string",
              "src_id": "string"
            }]
            '''})
        def post(self):
            '''
            Returns the applicable analytics.
            Not all analytics are applicable for every dataset. This request requires a list of inputs and will return the analytics options available based on those inputs.
            '''
            data = request.get_json()
            analytics = []

            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            cur = col.find()
            analytics = []
            if len(data) != 1:
                outputsPersist = []
                for res in data:
                    outputsPersist.extend(res['outputs'])
            else:
                outputsPersist = data[0]['outputs']
            for src in cur:
                contains = False
                outputs = outputsPersist[:]
                for i in src['inputs']:
                    if i in outputs:
                        contains = True
                        outputs.remove(i)
                    else:
                        contains = False
                        break
                if contains:
                    response = {key: value for key, value in src.items() if key != '_id'}
                    analytics.append(response)

            return analytics


    @ns_a.route('/clustering/')
    class Clustering(Resource):
        @api.doc(model='Analytic')
        def get(self):
            '''
            Returns a list of available clustering analytics.
            All analytics registered in the system with a type of 'Clustering' will be returned. If you believe there is an analytic that exists in the system but is not present here, it is probably not registered in the MongoDB database.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            cur = col.find()
            analytics = []
            for src in cur:
                if src['type'] == 'Clustering':
                    response = {key: value for key, value in src.items() if key != '_id'}
                    analytics.append(response)

            return analytics

    @ns_a.route('/classification/')
    class Classification(Resource):
        @api.doc(model='Analytic')
        def get(self):
            '''
            Returns a list of available classification analytics.
            All analytics registered in the system with a type of 'Classification' will be returned. If you believe there is an analytic that exists in the system but is not present here, it is probably not registered in the MongoDB database.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            cur = col.find()
            analytics = []
            for src in cur:
                if src['type'] == 'Classification':
                    response = {key: value for key, value in src.items() if key != '_id'}
                    analytics.append(response)

            return analytics

    @ns_a.route('/dimred/')
    class DimensionReduction(Resource):
        @api.doc(model='Analytic')
        def get(self):
            '''
            Returns a list of available dimension reduction analytics.
            All analytics registered in the system with a type of 'Dimension Reduction' will be returned. If you believe there is an analytic that exists in the system but is not present here, it is probably not registered in the MongoDB database.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            cur = col.find()
            analytics = []
            for src in cur:
                if src['type'] == 'Dimension Reduction':
                    response = {key: value for key, value in src.items() if key != '_id'}
                    analytics.append(response)

            return analytics

    @ns_a.route('/stats/')
    class Statistical(Resource):
        @api.doc(model='Analytic')
        def get(self):
            '''
            Returns a list of available statistical analytics.
            All analytics registered in the system with a type of 'Statistical' will be returned. If you believe there is an analytic that exists in the system but is not present here, it is probably not registered in the MongoDB database.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            cur = col.find()
            analytics = []
            for src in cur:
                if src['type'] == 'Statistical':
                    response = {key: value for key, value in src.items() if key != '_id'}
                    analytics.append(response)

            return analytics

    # @app.route('/analytics/<analytic_id>/', methods=['DELETE'])
    @ns_a.route('/<analytic_id>/')
    @api.doc(params={'analytic_id': 'The ID assigned to a particular analtyic'})
    class Analytic(Resource):
        @api.doc(responses={204: 'Resource removed successfully', 404: 'No resource at that URL'})
        def delete(self, analytic_id):
            '''
            Deletes specified analytic.
            This will permanently remove this analytic from the system. USE CAREFULLY!
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            try:
                analytic = col.find({'analytic_id':analytic_id})[0]

            except IndexError:
                return 'No resource at that URL.', 404

            else:
                col.remove({'analytic_id':analytic_id})
                os.remove(ANALYTICS_OPALS + analytic_id + '.py')

                return '', 204
        
        @api.doc(responses={200: 'Success', 404: 'No resource at that URL'})
        @api.doc(model='Analytic')
        def get(self, analytic_id):
            '''
            Returns the details of the specified analytic.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            try:
                analytic = col.find({'analytic_id':analytic_id})[0]
            except IndexError:
                try:
                    analytic = col.find({'name':analytic_id})[0]
                except IndexError:
                    return 'No resource at that URL.', 404

            else:
                return {key: value for key, value in analytic.items() if key != '_id'}

        @api.doc(responses={201: 'Success', 406: 'Error'})
        @api.doc(params={'payload': 'Must be a list of the model defined to the right.'}, body='Matrix')
        def post(self, analytic_id):
            '''
            Apply a certain analytic to the provided input data.
            The input must be a list of datasets, which can be matrices and/or results.

            '''
            #get the analytic
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            isResultSource = False

            #get the input data
            data = request.get_json(force=True)
            src_id = data['src'][0]['src_id']
            sub_id = data['src'][0]['id']
            parameters = data['parameters']
            inputs = data['inputs']
            name = data['name']
            res_id = utils.getNewId()
            #see if the input data is a result
            if 'analytic_id' in data['src'][0]:
                isResultSource = True
                mat_id = data['src'][0]['src_id']
            else:
                mat_id = sub_id
            storepath = RESUTLS_PATH + mat_id + '/' + res_id + '/'
            os.makedirs(storepath)

            #run analysis
            queue = Queue()
            # raise Exception(utils)
            p = Process(target=utils.run_analysis, args=(queue, analytic_id, parameters, inputs, storepath, name))
            p.start()
            p.join() # this blocks until the process terminates
            outputs = queue.get()
            if outputs != None:

                #store metadata
                res_col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
                try:
                    src = res_col.find({'src_id':mat_id})[0]

                except IndexError:
                    src = {}
                    src['rootdir'] = RESUTLS_PATH + mat_id + '/'
                    src['src'] = data['src'][0]
                    src['src_id'] = data['src'][0]['id']
                    src['results'] = []
                    res_col.insert(src)
                    src = res_col.find({'src_id':mat_id})[0]

                res = {}
                res['id'] = res_id
                res['rootdir'] = storepath
                res['name'] = name
                res['src_id'] = mat_id
                res['created'] = utils.getCurrentTime()
                res['analytic_id'] = analytic_id
                res['parameters'] = parameters
                res['outputs'] = outputs
                if isResultSource:
                    res['res_id'] = [ el['id'] for el in data['src'] ]
                results = []
                for each in src['results']:
                    results.append(each)
                results.append(res)
                res_col.update({'src_id':mat_id}, { '$set': {'results': results} })

                return res, 201
            else:
                out = subprocess.call('tail /var/www/bedrock/conf/error.log > /var/www/bedrock/error.txt', shell=True)
                # out = subprocess.call("sed -i 's/\[[a-zA-Z].*[0-9]\]//g' /var/www/bedrock/error.txt", shell=True)                    output.write(out)
                with open('/var/www/bedrock/error.txt') as out:
                    outcontent = out.read()
                return outcontent, 406

        @api.doc(params={'payload': 'Must be list of data to have classified.'}, responses={201: 'Success', 406: 'Error', 404: 'No resource at that URL'})
        def patch(self, analytic_id):
            '''
            Apply a certain analytic to the provided input data and return the classification label(s).
            This request is only applicable to analytics that are of type 'Classificaiton'.
            '''
            #get the analytic
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][ANALYTICS_COL_NAME]
            try:
                analytic = col.find({'analytic_id':analytic_id})[0]
            except IndexError:
                return 'No resource at that URL.', 404

            classname = analytic['classname']
            alg_type = analytic['type']

            #make sure it is of type 'Classification'
            if alg_type == 'Classification':
                return "This analytic is not of type 'Classification'", 406

            #get the input data
            data = request.get_json()
            parameters = data['parameters']
            inputs = data['inputs']
            result = analytics.classify(analytic_id, parameters, inputs)
            return result, 200

@ns_r.route('/')
class Results(Resource):
    @api.doc(model='Results')
    def get(self):
        '''
        Returns a list of available results.
        '''
        client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
        col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
        cur = col.find()
        results = []
        for src in cur:
            response = {key: value for key, value in src.items() if key != '_id'}
            results.append(response)

        return results

    # @api.doc(responses={204: 'Resource removed successfully'})
    @api.hide
    def delete(self):
        '''
        Deletes all stored results.
        '''
        client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
        col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
        #remove the entries in mongo
        col.remove({})
        #remove the actual files
        for directory in os.listdir(RESUTLS_PATH):
            file_path = os.path.join(RESUTLS_PATH, directory)
            shutil.rmtree(file_path)

        return '', 204

    @ns_r.route('/explorable/')
    class Explorable(Resource):
        @api.doc(model='Result')
        def get(self):
            '''
            Returns a list of explorable results.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
            cur = col.find()
            explorable = []
            for src in cur:
                for result in src['results']:
                    exp = {}
                    exp['rootdir'] = src['rootdir']
                    exp['src_id'] = src['src_id']
                    exp['id'] = result['id']
                    exp['outputs'] = result['outputs']
                    exp['name'] = result['name']
                    exp['created'] = result['created']
                    explorable.append(exp)

            return explorable

    @ns_r.route('/download/<src_id>/<res_id>/<output_file>/<file_download_name>/')
    class Download(Resource):
        def get(self,src_id,res_id,output_file,file_download_name):
            '''
            Downloads the specified result.
            Returns the specific file indicated by the user.
            '''

            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
            try:
                res = col.find({'src_id':src_id})[0]['results']
            except IndexError:
                response = {}
                # return ('No resource at that URL.', 404)
            else:
                for result in res:
                    if result['id'] == res_id:
                        return send_from_directory(result['rootdir'],output_file, as_attachment=True, attachment_filename=file_download_name)

            return 'No resource at that URL.', 404


    @ns_r.route('/<src_id>/')
    @api.doc(params={'src_id': 'The ID assigned to a particular result\'s source'})
    class ResultSrc(Resource):

        @api.doc(responses={204: 'Resource removed successfully', 404: 'No resource at that URL'})
        def delete(self, src_id):
            '''
            Deletes specified result tree.
            This will permanently remove this result tree from the system. USE CAREFULLY!

            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
            try:
                res = col.find({'src_id':src_id})[0]['results']

            except IndexError:
                return 'No resource at that URL.', 404

            else:
                col.remove({'src_id':src_id})
                shutil.rmtree(RESUTLS_PATH + src_id)
                return '', 204

        @api.doc(model='Results')
        def get(self, src_id):
            '''
            Returns the specified result tree.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
            try:
                res = col.find({'src_id':src_id})[0]

            except IndexError:
                response = {}
                # return ('No resource at that URL.', 404)

            else:
                response = {key: value for key, value in res.items() if key != '_id'}
            return response


    @ns_r.route('/<src_id>/<res_id>/')
    @api.doc(params={'src_id': 'The ID assigned to a particular result\'s source'})
    @api.doc(params={'res_id': 'The ID assigned to a particular result'})
    class Result(Resource):
        @api.doc(responses={204: 'Resource removed successfully', 404: 'No resource at that URL'})
        def delete(self, src_id,res_id):
            '''
            Deletes specified result.
            This will permanently remove this result from the system. USE CAREFULLY!
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
            try:
                res = col.find({'src_id':src_id})[0]['results']

            except IndexError:
                return 'No resource at that URL.', 404

            else:
                results_new = []
                found = False
                for each in res:
                    if each['id'] != res_id:
                        results_new.append(each)
                    else:
                        found = True
                if found:
                    col.update({'src_id':src_id}, { '$set': {'results': results_new} })
                else:
                    return 'No resource at that URL.', 404

                shutil.rmtree(RESUTLS_PATH + src_id + '/' + res_id)
                return '', 204

        @api.doc(responses={200: 'Success', 404: 'No resource at that URL'})
        @api.doc(model='Result')
        def get(self, src_id,res_id):
            '''
            Returns the specified result.
            '''
            client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
            col = client[ANALYTICS_DB_NAME][RESULTS_COL_NAME]
            try:
                res = col.find({'src_id':src_id})[0]['results']

            except IndexError:
                response = {}
                # return ('No resource at that URL.', 404)

            else:
                for result in res:
                    if result['id'] == res_id:
                        response = {key: value for key, value in result.items() if key != '_id'}

                        return {'result': response}

            return 'No resource at that URL.', 404

