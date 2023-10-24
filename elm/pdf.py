# -*- coding: utf-8 -*-
"""
ELM PDF to text parser
"""
import subprocess
import numpy as np
import requests
import copy
from PyPDF2 import PdfReader
import logging

from elm.base import ApiBase


logger = logging.getLogger(__name__)


class PDFtoTXT(ApiBase):
    """Class to parse text from a PDF document."""

    MODEL_ROLE = ('You clean up poorly formatted text '
                  'extracted from PDF documents.')
    """High level model role."""

    MODEL_INSTRUCTION = ('Text extracted from a PDF: '
                         '\n"""\n{}\n"""\n\n'
                         'The text above was extracted from a PDF document. '
                         'Can you make it nicely formatted? '
                         'Please only return the formatted text '
                         'without comments or added information.')
    """Instructions to the model with python format braces for pdf text"""

    def __init__(self, fp, page_range=None, model=None):
        """
        Parameters
        ----------
        fp : str
            Filepath to .pdf file to extract.
        page_range : None | list
            Optional 2-entry list/tuple to set starting and ending pages
            (python indexing)
        model : None | str
            Optional specification of OpenAI model to use. Default is
            cls.DEFAULT_MODEL
        """
        super().__init__(model)
        self.fp = fp
        self.raw_pages = self.load_pdf(page_range)
        self.pages = self.raw_pages
        self.full = self.combine_pages(self.raw_pages)

    def load_pdf(self, page_range):
        """Basic load of pdf to text strings

        Parameters
        ----------
        page_range : None | list
            Optional 2-entry list/tuple to set starting and ending pages
            (python indexing)

        Returns
        -------
        out : list
            List of strings where each entry is a page. This is the raw PDF
            text before GPT cleaning
        """

        logger.info('Loading PDF: {}'.format(self.fp))
        out = []
        pdf = PdfReader(self.fp)

        if page_range is not None:
            assert len(page_range) == 2
            page_range = slice(*page_range)
        else:
            page_range = slice(0, None)

        for i, page in enumerate(pdf.pages[page_range]):
            page_text = page.extract_text()
            if len(page_text.strip()) == 0:
                logger.debug('Skipping empty page {} out of {}'
                             .format(i + 1 + page_range.start, len(pdf.pages)))
            else:
                out.append(page_text)

        logger.info('Finished loading PDF.')
        return out

    def make_gpt_messages(self, pdf_raw_text):
        """Make the chat completion messages list for input to GPT

        Parameters
        ----------
        pdf_raw_text : str
            Raw PDF text to be cleaned

        Returns
        -------
        messages : list
            Messages for OpenAI chat completion model. Typically this looks
            like this:
                [{"role": "system", "content": "You do this..."},
                 {"role": "user", "content": "Please do this: {}"}]
        """

        query = self.MODEL_INSTRUCTION.format(pdf_raw_text)
        messages = [{"role": "system", "content": self.MODEL_ROLE},
                    {"role": "user", "content": query}]

        return messages

    def clean_txt(self):
        """Use GPT to clean raw pdf text in serial calls to the OpenAI API.

        Returns
        -------
        clean_pages : list
            List of clean text strings where each list entry is a page from the
            PDF
        """

        logger.info('Cleaning PDF text...')
        clean_pages = []

        for i, raw_page in enumerate(self.raw_pages):
            msg = self.make_gpt_messages(copy.deepcopy(raw_page))
            req = {"model": self.model, "messages": msg, "temperature": 0.0}

            kwargs = dict(url=self.URL, headers=self.HEADERS, json=req)

            try:
                response = requests.post(**kwargs)
                response = response.json()
            except Exception as e:
                msg = 'Error in OpenAI API call!'
                logger.exception(msg)
                response = {'error': str(e)}

            choice = response.get('choices', [{'message': {'content': ''}}])[0]
            message = choice.get('message', {'content': ''})
            content = message.get('content', '')
            clean_pages.append(content)
            logger.debug('Cleaned page {} out of {}'
                         .format(i + 1, len(self.raw_pages)))

        logger.info('Finished cleaning PDF.')

        self.pages = clean_pages
        self.full = self.combine_pages(self.pages)
        self.validate_clean()

        return clean_pages

    async def clean_txt_async(self, ignore_error=None, rate_limit=40e3):
        """Use GPT to clean raw pdf text in parallel calls to the OpenAI API.

        NOTE: you need to call this using the await command in ipython or
        jupyter, e.g.: `out = await PDFtoTXT.clean_txt_async()`

        Parameters
        ----------
        ignore_error : None | callable
            Optional callable to parse API error string. If the callable
            returns True, the error will be ignored, the API call will not be
            tried again, and the output will be an empty string.
        rate_limit : float
            OpenAI API rate limit (tokens / minute). Note that the
            gpt-3.5-turbo limit is 90k as of 4/2023, but we're using a large
            factor of safety (~1/2) because we can only count the tokens on the
            input side and assume the output is about the same count.

        Returns
        -------
        clean_pages : list
            List of clean text strings where each list entry is a page from the
            PDF
        """

        logger.info('Cleaning PDF text asyncronously...')

        all_request_jsons = []
        for page in self.raw_pages:
            msg = self.make_gpt_messages(page)
            req = {"model": self.model, "messages": msg, "temperature": 0.0}
            all_request_jsons.append(req)

        clean_pages = await self.call_api_async(self.URL, self.HEADERS,
                                                all_request_jsons,
                                                ignore_error=ignore_error,
                                                rate_limit=rate_limit)

        for i, page in enumerate(clean_pages):
            choice = page.get('choices', [{'message': {'content': ''}}])[0]
            message = choice.get('message', {'content': ''})
            content = message.get('content', '')
            clean_pages[i] = content

        logger.info('Finished cleaning PDF.')

        self.pages = clean_pages
        self.full = self.combine_pages(self.pages)
        self.validate_clean()

        return clean_pages

    def clean_poppler(self, fp_out):
        """Clean the pdf using the poppler pdftotxt utility

        Requires the `pdftotext` command line utility from this software:
            https://poppler.freedesktop.org/

        Parameters
        ----------
        fp_out : str
            Filepath to output .txt file

        Returns
        -------
        out : str
            Joined cleaned pages
        """
        stdout = subprocess.run(['pdftotext', '-layout',
                                 f"{self.fp}", f"{fp_out}"],
                                check=True, stdout=subprocess.PIPE)
        if stdout.returncode == 0:
            logger.info(f'Saved to disk: {fp_out}')
        else:
            raise RuntimeError(stdout)

        with open(fp_out, 'r') as f:
            clean_txt = f.read()

        # break on poppler page break
        self.pages = clean_txt.split('\x0c')
        remove = []
        for i, page in enumerate(self.pages):
            if not any(page.strip()):
                remove.append(i)
        for i in remove[::-1]:
            _ = self.pages.pop(i)

        self.full = self.combine_pages(self.pages)

        return self.full

    def validate_clean(self):
        """Run some basic checks on the GPT cleaned text vs. the raw text"""
        repl = ('\n', '.', ',', '-', '/', ':')

        if not any(self.full.replace('\n', '').strip()):
            msg = 'Didnt get ANY clean output text!'
            logger.error(msg)
            raise RuntimeError(msg)

        def replace_chars_for_clean(text):
            for char in repl:
                text = text.replace(char, ' ')
            return text

        for i, (raw, clean) in enumerate(zip(self.raw_pages, self.pages)):
            raw_words = replace_chars_for_clean(raw).split(' ')
            clean_words = replace_chars_for_clean(clean).split(' ')

            raw_words = {x for x in raw_words if len(x) > 2}
            clean_words = {x for x in clean_words if len(x) > 2}

            isin = sum(x in clean_words for x in raw_words)

            perc = 100
            if isin > 0 and len(raw_words) > 0:
                perc = 100 * isin / len(raw_words)

            if perc < 70:
                logger.warning('Page {} of {} has a {:.2f}% match with {} '
                               'unique words in the raw text.'
                               .format(i + 1, len(self.raw_pages), perc,
                                       len(raw_words)))
            else:
                logger.info('Page {} of {} has a {:.2f}% match with {} '
                            'unique words in the raw text.'
                            .format(i + 1, len(self.raw_pages), perc,
                                    len(raw_words)))

    @staticmethod
    def combine_pages(pages):
        """Combine pages of GPT cleaned text into a single string.

        Parameters
        ----------
        pages : list
            List of clean text strings where each list entry is a page from the
            PDF

        Returns
        -------
        full : str
            Single multi-page string
        """
        full = '\n'.join(pages)
        full = full.replace('\n•', '-')
        full = full.replace('•', '-')
        return full

    def clean_headers(self, char_thresh=0.6, page_thresh=0.8, split_on='\n',
                      iheaders=[0, 1, -2, -1]):
        """Clean headers/footers that are duplicated across pages

        Parameters
        ----------
        char_thresh : float
            Fraction of characters in a given header that are similar between
            pages to be considered for removal
        page_thresh : float
            Fraction of pages that share the header to be considered for
            removal
        split_on : str
            Chars to split lines of a page on
        iheaders : list
            Integer indices to look for headers after splitting a page into
            lines based on split_on. This needs to go from the start of the
            page to the end.

        Returns
        -------
        out : str
            Clean text with all pages joined
        """
        logger.info('Cleaning headers')
        headers = [None] * len(iheaders)
        tests = np.zeros((len(self.pages), len(headers)))

        page = self.pages[-1]
        for i, ih in enumerate(iheaders):
            headers[i] = page.split(split_on)[ih]

        for ip, page in enumerate(self.pages):
            for ih, header in zip(iheaders, headers):
                pheader = ''
                try:
                    pheader = page.split(split_on)[ih]
                except IndexError:
                    pass

                harr = header.replace(' ', '')
                parr = pheader.replace(' ', '')

                harr = harr.ljust(len(parr))
                parr = parr.ljust(len(harr))

                harr = np.array([*harr])
                parr = np.array([*parr])
                assert len(harr) == len(parr)

                test = harr == parr
                if len(test) == 0:
                    test = 1.0
                else:
                    test = test.sum() / len(test)

                tests[ip, ih] = test

        logger.debug('Header tests (page, iheader): \n{}'.format(tests))
        tests = (tests > char_thresh).sum(axis=0) / len(self.pages)
        tests = (tests > page_thresh)
        logger.debug('Header tests (iheader,): \n{}'.format(tests))

        for ip, page in enumerate(self.pages):
            page = page.split(split_on)
            for i, iheader in enumerate(iheaders):
                if tests[i]:
                    _ = page.pop(iheader)

            page = split_on.join(page)
            self.pages[ip] = page

        self.full = self.combine_pages(self.pages)
        return self.full
