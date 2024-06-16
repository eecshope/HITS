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

For step 3, you need to download the docker image and corresponding data volumn, which will be ready shortly