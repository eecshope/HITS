import asyncio
import json
import logging
from time import sleep
from typing import Optional, List

import requests
from urllib3.exceptions import SSLError, MaxRetryError

from generator.openlimit import ChatRateLimiter
from requests import ReadTimeout

from generator import api_process_parallel


class OpenGenerator:
    def __init__(self, key,
                 request_url,
                 model='gpt-3.5-turbo-1106',
                 monitor: Optional[ChatRateLimiter] = None):
        """
        monitor: monitor the token usage in multi-thread use
        """
        self.key = key
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {key}',
            'Connection': 'close'
        }
        self.request_url = request_url
        self.model = model
        self.monitor = monitor

    def generate_async(self, prompts, metas, save_filepath, temperature=0.2, gen_count=1, top_p=1, max_tokens=4096,
                       history: Optional[List[List]] = None):
        """
        Generate in async way calling OpenAI Codebook (modified version). Only support gpt-3.5-turbo
        :param save_filepath: file for saving the LLM's response
        :param max_tokens:
        :param top_p: top_p
        :param prompts: List[String]: the prompts
        :param metas: List[Dict]: The metas, should be aligned with prompts. Used to distinguish the output
        :param temperature: float, the temperature
        :param gen_count: the num of samples
        :param history: List of lists. Each sublist is a history. If len == 1, all history will be prepended to prompts
        :return: None
        """
        assert len(prompts) == len(metas)
        if history is not None:
            assert len(history) == 1 or len(history) == prompts
        messages_s = [[{"role": "user", "content": prompt}] for prompt in prompts]
        if history is not None:
            if len(history) == 1:
                for idx, message in enumerate(messages_s):
                    messages_s[idx] = history[0] + message
            else:
                for idx, message, h in enumerate(zip(messages_s, history)):
                    messages_s[idx] = history[idx] + h
        if 'gpt' in self.model:
            data_s = [{"model": self.model,
                       "messages": messages,
                       "temperature": temperature,
                       "top_p": top_p,
                       "n": gen_count,
                       "metadata": meta,
                       "max_tokens": max_tokens}
                      for messages, meta in zip(messages_s, metas)]
        else:
            data_s = list([])
            for i in range(gen_count):
                data_s += [{"model": self.model,
                            "messages": messages,
                            "temperature": temperature,
                            "top_p": top_p,
                            "n": 1,
                            "metadata": meta + f"_{i}",
                            "max_tokens": max_tokens}
                           for messages, meta in zip(messages_s, metas)]
        request_list = [json.dumps(data) for data in data_s]

        # begin executing async
        asyncio.run(
            api_process_parallel.process_api_requests(requests_list=request_list,
                                                      save_filepath=save_filepath,
                                                      request_url=self.request_url,
                                                      api_key=self.key,
                                                      max_requests_per_minute=5000 * 0.9 if 'gpt' in self.model else 30,
                                                      max_tokens_per_minute=160000 * 0.9,
                                                      token_encoding_name='cl100k_base',
                                                      max_attempts=5,
                                                      logging_level=logging.INFO)
        )

    def generate(self, prompt, system: Optional[str] = None, temperature=0.2, gen_count=1, top_p=1.0, history=None,
                 timeout=600):
        """
        Generate given prompt following the temperature and gen_count set
        :param top_p:
        :param timeout:
        :param gen_count:
        :param temperature:
        :param prompt: a string, the user information
        :param system: a string, the system information
        :param history:
        :return: the generated openai response
        """

        if history is None:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = history.append({"role": "user", "content": prompt})

        if system is not None:
            if messages[0]['role'] == 'system':
                messages[0]['content'] = system
            else:
                messages = [{"role": "system", "content": system}] + messages
                # messages = messages + [{"role": "system", "content": system}]

        data = {"model": self.model,
                "messages": messages,
                "temperature": temperature,
                "n": gen_count,
                "top_p": top_p}
        data = json.dumps(data)

        try:
            trial_cnt = 0
            while trial_cnt < 5:
                try:
                    if self.monitor is not None:
                        with self.monitor.limit(data):
                            response = requests.post(self.request_url,
                                                     headers=self.headers,
                                                     data=data,
                                                     timeout=timeout)
                    else:
                        response = requests.post(self.request_url,
                                                 headers=self.headers,
                                                 data=data,
                                                 timeout=timeout)

                    if response.status_code == 200:
                        outputs = [choice['message']['content'] for choice in response.json()['choices']]
                        token_count = {"prompt_tokens": response.json()['usage']['prompt_tokens'],
                                       "completion_tokens": response.json()['usage']['completion_tokens']}
                        return response.status_code, outputs, token_count
                    else:
                        logging.warning(f"Network error happen: status code {response.status_code}. Sleep 10s to rest")
                        logging.warning(f"The message is {response.content}")
                        sleep(10)
                except (SSLError, MaxRetryError) as e:
                    logging.warning(f"Network {e} happened. Sleep 10s to rest")
                    trial_cnt += 1
                    sleep(10)
            return response.status_code, None, None
        except ReadTimeout:
            return "timeout", None, None
