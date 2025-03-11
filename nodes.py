from langchain_core.messages import SystemMessage, HumanMessage

class Nodes:
    
    def get_related_topics(self, topic: str):
        messages = [
            SystemMessage(
                content="""You are a professional researcher. Your job is to find the related topics for the provided topic. You need to find the topics that are closely \
                related to the provided topic and are important for the research document. You need to provide a list of related topics such that they can be directly searched \
                about to get relavent articles or research papers. Be very comprehensive and specific."""
            ),
            HumanMessage(
                content=f"""Find the related topics for the topic {topic}."""
            )
        ]

        return messages
    
    def get_outline(self, document: str):
        messages = [
            SystemMessage(
                content="""You are a professional researcher. Your job is to analyze the provided research document and extract the outline of the document. You need to \
                extract the major sections and subsections of the research document with their descriptions and basic information about the content under each of them. Be very \
                comprehensive and specific."""
            ),
            HumanMessage(
                content=f"""Extract the outline of the provided research document.
                
                {document}"""
            )
        ]

        return messages
    
    def generate_outline(self, topic: str, output_format: str, outlines: str):
        messages = [
            SystemMessage(
                content=f"""You are an expert research document writer. Your job is to write the detailed outline of a research document for the provided topic and provided \
                type of research document. The outline should consist of all the important major sections and subsections of the research document with their descriptions and \
                basic information about the content under each of them. Do not add conclusion and references as subsections at the end of each section. They should be separate \
                sections at the end of the document. Be very comprehensive and specific.
                
                You can also refer to the provided outlines for some documents related to the topic for inspiration."""
            ),
            HumanMessage(
                content=f"""Write the outline of a research document in the format {output_format} and on the topic {topic}.
                
                You can take inspiration from the following outlines:
                {outlines}"""
            )
        ]

        return messages
    
    def generate_perspectives(self, topic: str, outlines: str):
        messages = [
            SystemMessage(
                content=f"""You are a professional researcher. Your job is to generate the perspectives for the provided topic. You need to select diverse and distinct group \
                of professionals who will work together to create a comprehensive research document on the provided topic. Each of them represents a different perspective, \
                role, or affiliation related to this topic.
                You can use other reseach documents or articles of related topics for inspiration. For each professional, add a description of what they will focus on.
                Outlines of the research document of related topics:
                {outlines}"""
            ),
            HumanMessage(
                content=f"""Generate the perspectives for the topic {topic}."""
            )
        ]

        return messages
    
    def perspective_agent(self, perspective: str, topic: str, output_format: str, outline: str, section: str):
        messages = [
            SystemMessage(
                content=f"""You are {perspective}

                You are helping in writing a research document on the topic {topic} in {output_format} format with the outline:
                {outline}

                You have access to the following tool which you can use to write the content for the provided section of the research document:
                vector_search_tool - This tool would help you retrieve the relevant documents from the vector store based on the search query which would be in string format \
                and would consist keywords or phrases, but do not use AND, OR, NOT operators, instead, call this tool multiple times at once with different keywords or phrases

                You can call this tool either sequentially or together as well.
                
                Analyse the topic of research and the outline of the research document, fetch relevant documents from vector store until you think you have all the \
                information you would require to write the content for the provided section.
                
                Then keep in mind the format of the research document and write the content for the section in a detailed and comprehensive manner. Do not forget to cite your \
                sources."""
            ),
            HumanMessage(
                content=f"""Please generate the content for the following section:
                {section}"""
            )
        ]

        return messages
    
    def generate_combined_section(self, section_content: str, topic: str, outline: str, section: str):
        messages = [
            SystemMessage(
                content=f"""You are a professional researcher and writer who is helping with the research document on the topic {topic} with the following outline:
                {outline}

                Your job is to analyse the content written by different professionals for the section {section} and combine them into a single coherent section. You need to \
                make sure that the content is well-structured, coherent, and comprehensive."""
            ),
            HumanMessage(
                content=f"""Write the combined section for the section:
                
                {section}
                
                These are the provided content by different professionals:
                {section_content}"""
            )
        ]

        return messages