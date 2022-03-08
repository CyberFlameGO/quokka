import pickle
import pyarrow.csv as csv
import pyarrow.parquet as pq
import pandas as pd
from io import BytesIO, StringIO
import boto3
import s3fs
import time
import redis

# this is used to convert an RDD into streams
# gonna do some intelligent stuff by maximizing data locality
class RedisObjectsDataset:

    # expects objects as a dict of channel : list of tuples of (ip, key, size)
    def __init__(self, channel_objects, ip_set) -> None:
        self.channel_objects = channel_objects
        self.rs = {}
        self.ip_set = ip_set
        for ip in self.ip_set:
            self.rs[ip] = redis.Redis(host=ip, port=6800, db=0)

    def get_next_batch(self, mapper_id, pos = None):
        if mapper_id not in self.channel_objects:
            raise Exception("ERROR: I dont know about where this channel is. Autoscaling here not supported yet. Will it ever be?")
        
        total_objects = len(self.channel_objects[mapper_id])

        if pos is None:
            pos = 0

        while pos < total_objects:
            object = self.channel_objects[mapper_id][pos]
            bump =  self.rs[object[0]].get(object[1])
            pos += 1
            yield pos, pickle.loads(bump)


class InputSingleParquetDataset:

    def __init__(self, bucket, filename, columns = None) -> None:
        s3 = s3fs.S3FileSystem()
        self.parquet_file = pq.ParquetFile(s3.open(bucket + filename, "rb"))
        self.num_row_groups = self.parquet_file.num_row_groups
        self.num_mappers = None
        self.columns = columns

    def set_num_mappers(self, num_mappers):
        self.num_mappers = num_mappers
    
    def get_next_batch(self, mapper_id, pos = None):
        assert self.num_mappers is not None
        if pos is None:
            curr_row_group = mapper_id 
        else:
            curr_row_group = pos
        while curr_row_group < len(self.num_row_groups):
            a = self.parquet_file.read_row_group(curr_row_group, columns = self.columns).to_pandas()
            yield curr_row_group, a

# use this if you have a lot of small parquet files
class InputMultiParquetDataset:

    # filter pushdown could be profitable in the future, especially when you can skip entire Parquet files
    # but when you can't it seems like you still read in the entire thing anyways
    # might as well do the filtering at the Pandas step. Also you need to map filters to the DNF form of tuples, which could be 
    # an interesting project in itself. Time for an intern?

    def __init__(self, bucket, prefix, columns = None, filters = None) -> None:
        self.s3 = boto3.client('s3')
        self.bucket = bucket
        z = self.s3.list_objects_v2(Bucket = bucket,Prefix=prefix)
        self.files = [i['Key'] for i in z['Contents'] if i['Key'].endswith(".parquet")]
        self.num_mappers = None
        self.columns = columns
        self.filters = filters
        while 'NextContinuationToken' in z.keys():
            z = self.s3.list_objects_v2(Bucket = "tpc-h-parquet",Prefix="lineitem",ContinuationToken = z['NextContinuationToken'])
            self.files.extend([i['Key'] for i in z['Contents'] if i['Key'].endswith(".parquet")])
    
    def set_num_mappers(self, num_mappers):
        self.num_mappers = num_mappers

    def get_next_batch(self, mapper_id, pos = None):
        assert self.num_mappers is not None
        if pos is None:
            curr_pos = mapper_id 
        else:
            curr_pos = pos
        while curr_pos < len(self.files):
            print("starting reading ",time.time())
            a = pq.read_table("s3://" + self.bucket + "/" + self.files[curr_pos],columns=self.columns, filters = self.filters).to_pandas()
            print("ending reading ",time.time())
            curr_pos += self.num_mappers
            yield curr_pos, a

class InputCSVDataset:

    def __init__(self, bucket, key, names, id, sep= ",", stride = 64 * 1024 * 1024) -> None:

        self.s3 = boto3.client('s3') # needs boto3 client
        self.bucket = bucket
        self.key = key
        self.num_mappers = None
        self.names = names
        self.id = id
        self.sep = sep
        self.stride = stride
    
    def set_num_mappers(self, num_mappers):
        self.num_mappers = num_mappers
        self.length, self.adjusted_splits = self.get_csv_attributes()

    def get_csv_attributes(self, window = 1024 * 32):

        if self.num_mappers is None:
            raise Exception
        splits = 64

        response = self.s3.head_object(
            Bucket=self.bucket,
            Key=self.key
        )
        length = response['ContentLength']
        assert length // splits > window * 2
        potential_splits = [length//splits * i for i in range(splits)]
        #adjust the splits now
        adjusted_splits = []

        # the first value is going to be the start of the second row 
        # -- we assume there's a header and skip it!

        resp = self.s3.get_object(Bucket=self.bucket,Key=self.key, Range='bytes={}-{}'.format(0, window))['Body'].read()

        first_newline = resp.find(bytes('\n','utf-8'))
        if first_newline == -1:
            raise Exception
        else:
            adjusted_splits.append(first_newline)

        for i in range(1, len(potential_splits)):
            potential_split = potential_splits[i]
            start = max(0,potential_split - window)
            end = min(potential_split + window, length)
            
            resp = self.s3.get_object(Bucket=self.bucket,Key=self.key, Range='bytes={}-{}'.format(start, end))['Body'].read()
            last_newline = resp.rfind(bytes('\n','utf-8'))
            if last_newline == -1:
                raise Exception
            else:
                adjusted_splits.append(start + last_newline)
        
        adjusted_splits[-1] = length 
        
        print(length, adjusted_splits)
        return length, adjusted_splits

    def get_next_batch(self, mapper_id, pos = None): #default is to get 16 KB batches at a time. 
        
        if self.num_mappers is None:
            raise Exception("I need to know the total number of mappers you are planning on using.")

        splits = len(self.adjusted_splits)
        assert self.num_mappers < splits + 1
        assert mapper_id < self.num_mappers + 1
        chunks = splits // self.num_mappers
        if pos is None:
            start = self.adjusted_splits[chunks * mapper_id]
            pos = start
        
        if mapper_id == self.num_mappers - 1:
            end = self.adjusted_splits[splits - 1]
        else:
            end = self.adjusted_splits[chunks * mapper_id + chunks] 

        while pos < end-1:

            resp = self.s3.get_object(Bucket=self.bucket,Key=self.key, Range='bytes={}-{}'.format(pos,min(pos+self.stride,end)))['Body'].read()

            last_newline = resp.rfind(bytes('\n','utf-8'))

            #import pdb;pdb.set_trace()
            
            if last_newline == -1:
                raise Exception
            else:
                resp = resp[:last_newline]
                pos += last_newline
                print("start convert,",time.time())
                #bump = pd.read_csv(BytesIO(resp), names =self.names, sep = self.sep, index_col = False)
                bump = csv.read_csv(BytesIO(resp),read_options = csv.ReadOptions(column_names=self.names), parse_options=csv.ParseOptions(delimiter=self.sep)).to_pandas() 
                print("done convert,",time.time())
                yield pos, bump


class OutputCSVDataset:

    def __init__(self, bucket, key, id) -> None:

        self.s3 = boto3.client('s3') # needs boto3 client
        self.bucket = bucket
        self.key = key
        self.id = id
        self.num_reducers = None

        self.multipart_upload = self.s3.create_multipart_upload(
            Bucket=bucket,
            Key=key,
        )

        self.parts = []

    def set_num_reducer(self, num_reducer):
        self.num_reducers = num_reducer
        chunks = 10000 // num_reducer
        self.reducer_current_part = [(i * chunks + 1) for i in range(num_reducer)]
        self.reducer_partno_limit = self.reducer_current_part[1:] + [10000]

    def upload_chunk(self, df, reducer_id):
        if self.num_reducers is None:
            raise Exception("I need to know the number of reducers")

        current_part = self.reducer_current_part[reducer_id]
        if current_part == self.reducer_partno_limit[reducer_id] - 1:
            raise Exception("ran out of part numbers")
        
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, header = (True if current_part == 1 else False))
        
        uploadPart = self.s3.upload_part(
            Bucket = self.bucket, 
            Key = self.key, 
            UploadId = self.multipart_upload['UploadId'],
            PartNumber = current_part,
            Body = csv_buffer.getvalue()
        )

        self.reducer_current_part[reducer_id] += 1
        
        self.parts.append({
            'PartNumber': current_part,
            'ETag': uploadPart['ETag']
        })
        
