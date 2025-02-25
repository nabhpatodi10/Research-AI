from langchain_core.messages import SystemMessage, HumanMessage

class Nodes:

    def generate_outline(self, topic: str, output_format: str):
        messages = [
            SystemMessage(
                content=f"""You are an expert research document writer. Your job is to write the detailed outline of a research document for the provided topic and provided \
                type of research document. The outline should consist of all the important major sections and subsections of the research document with their descriptions and \
                basic information about the content under each of them. Be very comprehensive and specific."""
            ),
            HumanMessage(
                content=f"""Write the outline of a research document in the format {output_format} and on the topic {topic}."""
            )
        ]

        return messages
    
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