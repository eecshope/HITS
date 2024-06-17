# Repository for SlicePromptTest4J

This is the source code repo for SlicePromptTest4J. This repo supports you to inspect
1. The detailed implementation of our prompt design (COT-procedures, instructions and examples)
2. The detailed implementation of the whole working procedure
3. Code to reproduce the experiment results

For step 1, we recommend you read the prompts in Dir `prompts` directly. The prompts are implemented using `jinja2` templates. 

For step 2, we recommend you start from Dir `scripts`. The working process is 
1. Create workspace for each method-to-test via `create_workspace.py`
2. Generate slices for methods-to-test via `prompt_slice_parallel.py`
3. Generate init test suites via `prompt_init_parallel.py`
4. Execute and fix the test suites via `prompt_fix_parallel.py`

For step 3, you need to download the dataset provided via the private link [url]https://figshare.com/s/6f9d74f2e17c77d0700c and following these steps:

1. create a directory and decompress everything provided in the link
2. start a mongodb server and add everything in the dataset to the database. Each directory in the dataset corresponds to a collection for one project-to-test
3. start a docker container from a conda image and login as 'root'
   1. Be aware that map the directory created in step 1 to the container as `/root/experiments` 
4. install dependencies provided in this repo to the container
5. install java 17 to the container
6. Edit the `config_template.ini` and save as `config.ini`. You need to set:
   1. mondo db info
   2. openai info
6. Generate test cases following the procedures in step 2. 

If you don't want to execute the whole generation process, we also provide the test cases already generated in the link provided above.