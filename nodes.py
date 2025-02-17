from langchain_core.messages import SystemMessage, HumanMessage

class Nodes:

    def generate_search_queries(self, topic: str, output_format: str):
        messages = [
            SystemMessage(
                content = """You are an expert in generating search queries to gather information from the internet. Your job is to generate exactly 10 search queries on a \
                given topic such that extensive research can be done using those search queries. The search queries should cover all the aspects of the topic like latest \
                trends or news or current affairs, history of that topic or comparisons or gethering existing studies or researches done on same or similar topics and more \
                depending on the topic to perfom a very detailed and extensive research. The research topic and what kind of a document has to be made from the research will \
                be given to you, the search queries should be made keeping in mind both the things.
                Give the output as a list containing only these 10 search queries as individual string elements, nothing else."""
            ),
            HumanMessage(
                content = f"""Give me the search queries for the following topic and the following document type:\
                
                Topic: {topic}\

                Output Document: {output_format}"""
            )
        ]
        return messages
    
    def first_plan_document(self, topic: str, output_format: str, queries: list[str]):
        messages = [
            SystemMessage(
                content = """You are an expert in planning the structure of documents based on the given main topic of the document, the type of the document and the search \
                queries used to gather information for this document. Your job is to think about the headings, sub-headings, topics and sub-topics for a research document for \
                the given main topic, the type of the document and the search queries. The headings or sub-headings or topics or sub-topics should be such that they cover all \
                the aspects of the given main topic and they should be such that the document covers everything which can be researched about the given main topic. Keep in \
                mind that these headings or sub-headings or topics or sub-topics will be the structure of the document, which means that the entire content of the document \
                will be placed under these. Also keep in mind that all search queries might not produce results which the query aims for, and the information collected might \
                be around those search queries as well. So the topics or sub-topics or headings or sub-headings must not only be dependent on these search queries but majorly \
                on the main topic and the type of document, the search queries are only to give you a very slight idea about the information collected.
                Give the output as a list containing only these headings or sub-headings or topics or sub-topics as individual string elements and nothing else."""
            ),
            HumanMessage(
                content = f"""Give me the headings or sub-headings or topics or sub-topics for the following main topic and the following document type:\
                    
                Main Topic: {topic}\

                Output Document: {output_format}\

                Search Queries: {queries}"""
            )
        ]
        return messages
    
    def next_plan_document(self, topic: str, output_format: str, queries: list[str], plan: list[str], index: int):
        messages = [
            SystemMessage(
                content = f"""You are an expert in planning the structure of documents based on the given main topic of the document, the type of the document, the search \
                queries used to gather information for this document and the previously decided structure of the document. Your job is to think about the headings, \
                sub-headings, topics and sub-topics for a research document for the given main topic, the type of the document, the search queries and the previously selected \
                list of headings, sub-headings, topics or sub-topics. The headings or sub-headings or topics or sub-topics should be such that they cover all \
                the aspects of the given main topic and they should be such that the document covers everything which can be researched about the given main topic. Keep in \
                mind that these headings or sub-headings or topics or sub-topics will be the structure of the document, which means that the entire content of the document \
                will be placed under these. Also keep in mind that all search queries might not produce results which the query aims for, and the information collected might \
                be around those search queries as well. So the topics or sub-topics or headings or sub-headings must not only be dependent on these search queries but majorly \
                on the main topic, the type of document and previous structure of the document, the search queries are only to give you a very slight idea about the \
                information collected. Also note that you do not have to necessarily change the entire previously decided structure of the document, you can just add the \
                required headings, sub-headings, topics or sub-topics to the previous structure or remove the non required ones. But before you do that, be very careful to not \
                remove the first {index} headings, sub-headings, topics or sub-topics as the content for those has already been generated and finalised and that cannot be \
                changed.
                Give the output as a list containing only these headings or sub-headings or topics or sub-topics as individual string elements and nothing else."""
            ),
            HumanMessage(
                content = f"""Give me the headings or sub-headings or topics or sub-topics for the following main topic and the following document type:\
                    
                Main Topic: {topic}\

                Output Document: {output_format}\

                Search Queries: {queries}\

                Previous Structure: {plan}\

                Please remember to not change or remove the first {index} headings or sub-headings or topics or sub-topics from the given previous structure as their content \
                has been finalised and it cannot be changed"""
            )
        ]
        return messages
    
    def generate_vector_queries(self, topic: str, output_format: str, heading: str):
        messages = [
            SystemMessage(
                content = """You are an expert in generating search queries to gather information from vector stores which contain information about the given topic. Your job \
                is to generate exactly 10 search queries on a given main topic and a specific heading or sub-heading or topic or sub-topic related to the given topic which will \
                be a part of the final document. These vector store search queries should aim to gather maximum information about the given heading or sub-heading or topic or \
                sub-topic under the main topic such that proper content can be generated for the given heading or sub-heading or topic or sub-topic based on that information \
                for the given document type. Note that same process will be repeated for other topics as well, so the vector store search queries must only focus on getting \
                information which can be written under the given heading or sub-heading or topic or sub-topic for the given type of document. These queries have to be keywords \
                or phrases which you are looking for, do not go for AND, OR, NOT operators in these queries and do not use _ in between words, there can be multiple words in \
                the search query, these queries are only supposed to be simple string values for which the search will be done. These strings will be used as it is for \
                searching so the output should only be the search queries.
                Give the output as a list containing only these 10 vector store search queries as individual string elements, nothing else."""
            ),
            HumanMessage(
                content = f"""Give me the vector store search queries for the following main topic which should aim to gather maximum important information under the following \
                heading or sub-heading or topic or sub-topic and the following document type:\
                
                Main Topic: {topic}\
                
                Heading or Sub-heading or topic or sub-topic: {heading}

                Output Document: {output_format}"""
            )
        ]
        return messages
    
    def generate_content(self, topic: str, plan: str, heading: str, information: str):
        messages = [
            SystemMessage(
                content = f"""You are an expert in writing content for research documents. Your job is to write a part of a research document in extreme detail and accuracy. \
                You will be given the main topic of the document, the structure of the document which will be a list of all the headings and sub-headings of the document, the \
                heading or sub-heading under which you will have to write the content which will be a part of the research document under that heading and the knowledge base \
                which you have to refer while writing that content. Keep in mind that you strictly have to stick to the mentioned heading or sub-heading for which you have to \
                write the content and whatever you write should be from the knowledge base given, do not make things up on your own and do not write things which are not in the \
                given knowledge base. Keep in mind that you are writing a part of a very important research document so you have to write an extremely detailed, lengthy and \
                accurate content which should completely be based on the knowledge base given but also keep in mind that the content you generate should be like a part of a \
                research document under the given heading name, for example, if the given heading is 'introduction', then the generated content should be the introduction \
                of that research document, if the given heading is 'A Comparitive Study between LangChain and LangGraph', then the generated content should talk about LangChain \
                and LangGraph and show a comparitive study like it would in any similar research document, do not deviate off the heading or sub-heading. Use proper new line \
                characters for new paragraphs and divide the content into paragraphs, do not give a single lengthy paragraph. Do not use html tags like <p> or <h> or <ol> or \
                <ul> or any kind of scripting language, the output should be simple text containing the heading and the detailed, lengthy, acurate, factual and paragraphed \
                content. Remember to strictly follow the heading or sub-heading, you only have to write about that and focus on writing as much as possible on it. The given \
                heading or sub-heading should be the heading for your generated content."""
            ),
            HumanMessage(
                content = f"""Write the content for the researh document of the following main topic, following heading or Sub-heading or topic or sub-topic, with the \
                following knowledge base and the following type of document:\
                
                Main Topic: {topic}\
                
                Document Structure: {plan}\
                
                Heading or Sub-heading on which you have to generate content: {heading}\

                Knowledge Base: {information}"""
            )
        ]
        return messages
    
    def planning_check(self, topic: str, output_format: str, queries: list[str], plan: list[str]):
        messages = [
            SystemMessage(
                content = f"""You are an expert in analysing whether the given structure of a document is good enough or not based on the given main topic of the document, \
                the type of the document, the search queries used to gather information for this document and the previously decided structure of the document. Your job is \
                to analyse the headings, sub-headings, topics and sub-topics for a research document for the given main topic, the type of the document, the search queries \
                and the previously selected list of headings, sub-headings, topics or sub-topics. The headings or sub-headings or topics or sub-topics should be such that \
                they cover all the aspects of the given main topic and they should be such that the document covers everything which can be researched about the given main \
                topic. Keep in mind that these headings or sub-headings or topics or sub-topics will be the structure of the document, which means that the entire content of \
                the document will be placed under these. Also keep in mind that all search queries might not produce results which the query aims for, and the information \
                collected might be around those search queries as well, the search queries are only to give you a very slight idea about the information collected.
                Give the output as a boolean value only where True means that re-planning or re-structuring the document is necessary and False means that no re-planning or \
                re-structuring is required for the document, the previously decided one is good enough according to the main topic and the document type."""
            ),
            HumanMessage(
                content = f"""Tell me if re-planning or re-structuring is required for the document with the following main topic, the following document type, the following \
                search queries and the following previously decided structure:\
                    
                Main Topic: {topic}\

                Output Document: {output_format}\

                Search Queries: {queries}\

                Previous Structure: {plan}"""
            )
        ]
        return messages
    
    def information_check(self, topic: str, output_format: str, heading: str, information: str):
        messages = [
            SystemMessage(
                content = f"""You are an expert in analysing whether the given knowledge base is good enough for a research document of the given main topic, given heading or \
                sub-heading and the given output document type. Your job is to analyse the knowledge base and tell if it is good enough or not based on the given the main topic \
                of the document, the heading or sub-heading and output document type. Keep in mind that this knowledge base will be used to write the content under the given \
                heading or sub-heading for a very important research document in the future so if the knowledge base is not suffcient or doesn't have good quality or accurate \
                information, then it should be changed. This knowledge base will only be used to generate the content under the given heading or sub-heading and not for the \
                entire research document, so analyse the knowledge base accordingly. For exapmle, if the heading is 'introduction', then the knowledge base should have all the \
                information which can be used to write the introduction of the research document, if the heading is 'A Comparitive Study between LangChain and LangGraph', then \
                the knowledge base should have all the information about LangChain, LangGraph and enough information to write a comparitive study between the two according to \
                the research document.
                Give the output as a boolean value where True means that the knowledge base is good enough to write the content based on it and False means that the knowledge \
                base is not good enough and that improvements should be made to it before writing the content based on it."""
            ),
            HumanMessage(
                content = f"""Analyse the knowledge base for the researh document of the following main topic, following heading or sub-heading or topic or sub-topic, with the \
                following type of output document:\
                
                Main Topic: {topic}\
                
                Heading or Sub-heading or topic or sub-topic: {heading}

                Knowledge Base: {information}

                Output Document: {output_format}"""
            )
        ]
        return messages
    
    def content_check(self, topic: str, output_format: str, heading: str, information: str, content: str):
        messages = [
            SystemMessage(
                content = f"""You are an expert in analysing whether the given content is good enough for a research document of the given main topic, given heading or \
                sub-heading or topic or sub-topic, the knowledge base used to generate that content and the given output document type. Your job is to analyse the content and \
                tell if it is good enough or not based on the given the main topic of the document, the heading or sub-heading or topic or sub-topic, the knowledge base used to \
                generate that content and output document type. Keep in mind that this content will be a part of a very important research document and if it is not up to the \
                mark with the quality of information or if there are any factual mistakes in the content based on the knowledge base given, then it should be changed. Also if \
                the content doesn't have all the information which it should have based on the knowledge base or if the content is too short based on the given heading and the \
                knowledge base, then it should be re-written
                Give the output as a boolean value where True means that the content is good enough to be a part of the research document and False means that the content \
                is not good enough and that improvements should be made to it before adding it to the research document."""
            ),
            HumanMessage(
                content = f"""Analyse the content for the researh document of the following main topic, following heading or sub-heading or topic or sub-topic, following \
                knowledge base with the following type of output document:\
                
                Main Topic: {topic}\
                
                Heading or Sub-heading or topic or sub-topic: {heading}

                Knowledge Base: {information}

                Output Document: {output_format}

                Content to be analysed: {content}"""
            )
        ]
        return messages