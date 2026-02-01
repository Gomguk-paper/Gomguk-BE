from datetime import datetime
from sqlmodel import Session, select, text
from app.core.db import engine
from app.models.paper import Paper, PaperTag, Tag
from app.core.enums import Site

def utcnow():
    return datetime.now()

# Dummy Data from frontend
papers_data = [
  {
    "id": "p1",
    "title": "백엔드 테스트용 제목1",
    "authors": ["Vaswani, A.", "Shazeer, N.", "Parmar, N."],
    "year": 2017,
    "venue": "NeurIPS",
    "tags": ["Transformer", "NLP", "Attention"],
    "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
    "pdfUrl": "https://arxiv.org/pdf/1706.03762",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p2",
    "title": "백엔드 테스트용 제목2",
    "authors": ["Devlin, J.", "Chang, M.", "Lee, K."],
    "year": 2019,
    "venue": "NAACL",
    "tags": ["NLP", "Transformer", "Pre-training"],
    "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers...",
    "pdfUrl": "https://arxiv.org/pdf/1810.04805",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p3",
    "title": "Denoising Diffusion Probabilistic Models",
    "authors": ["Ho, J.", "Jain, A.", "Abbeel, P."],
    "year": 2020,
    "venue": "NeurIPS",
    "tags": ["Diffusion", "Generative", "Vision"],
    "abstract": "We present high quality image synthesis results using diffusion probabilistic models...",
    "pdfUrl": "https://arxiv.org/pdf/2006.11239",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p4",
    "title": "Proximal Policy Optimization Algorithms",
    "authors": ["Schulman, J.", "Wolski, F.", "Dhariwal, P."],
    "year": 2017,
    "venue": "arXiv",
    "tags": ["RL", "Policy Gradient", "Optimization"],
    "abstract": "We propose a new family of policy gradient methods for reinforcement learning...",
    "pdfUrl": "https://arxiv.org/pdf/1707.06347",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p5",
    "title": "Vision Transformer (ViT)",
    "authors": ["Dosovitskiy, A.", "Beyer, L.", "Kolesnikov, A."],
    "year": 2021,
    "venue": "ICLR",
    "tags": ["Vision", "Transformer", "Image Classification"],
    "abstract": "While the Transformer architecture has become the de-facto standard for NLP tasks, its applications to computer vision remain limited...",
    "pdfUrl": "https://arxiv.org/pdf/2010.11929",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p6",
    "title": "GPT-4 Technical Report",
    "authors": ["OpenAI"],
    "year": 2023,
    "venue": "arXiv",
    "tags": ["LLM", "Multimodal", "Scaling"],
    "abstract": "We report the development of GPT-4, a large-scale multimodal model which can accept image and text inputs...",
    "pdfUrl": "https://arxiv.org/pdf/2303.08774",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p7",
    "title": "Reinforcement Learning from Human Feedback",
    "authors": ["Christiano, P.", "Leike, J.", "Brown, T."],
    "year": 2017,
    "venue": "NeurIPS",
    "tags": ["RL", "RLHF", "Human Feedback"],
    "abstract": "For sophisticated reinforcement learning systems to interact usefully with real-world environments...",
    "pdfUrl": "https://arxiv.org/pdf/1706.03741",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p8",
    "title": "Stable Diffusion",
    "authors": ["Rombach, R.", "Blattmann, A.", "Lorenz, D."],
    "year": 2022,
    "venue": "CVPR",
    "tags": ["Diffusion", "Vision", "Generative"],
    "abstract": "We present high-resolution image synthesis with latent diffusion models...",
    "pdfUrl": "https://arxiv.org/pdf/2112.10752",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p9",
    "title": "Chain-of-Thought Prompting",
    "authors": ["Wei, J.", "Wang, X.", "Schuurmans, D."],
    "year": 2022,
    "venue": "NeurIPS",
    "tags": ["LLM", "Prompting", "Reasoning"],
    "abstract": "We explore how generating a chain of thought -- a series of intermediate reasoning steps...",
    "pdfUrl": "https://arxiv.org/pdf/2201.11903",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p10",
    "title": "ResNet: Deep Residual Learning",
    "authors": ["He, K.", "Zhang, X.", "Ren, S."],
    "year": 2016,
    "venue": "CVPR",
    "tags": ["Vision", "CNN", "Deep Learning"],
    "abstract": "Deeper neural networks are more difficult to train. We present a residual learning framework...",
    "pdfUrl": "https://arxiv.org/pdf/1512.03385",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p11",
    "title": "Constitutional AI",
    "authors": ["Bai, Y.", "Kadavath, S.", "Kundu, S."],
    "year": 2022,
    "venue": "arXiv",
    "tags": ["LLM", "Safety", "Alignment"],
    "abstract": "We discuss a method we call Constitutional AI (CAI) for training harmless AI assistants...",
    "pdfUrl": "https://arxiv.org/pdf/2212.08073",
    "imageUrl": "/mockup_thumb.jpg",
  },
  {
    "id": "p12",
    "title": "Segment Anything (SAM)",
    "authors": ["Kirillov, A.", "Mintun, E.", "Ravi, N."],
    "year": 2023,
    "venue": "ICCV",
    "tags": ["Vision", "Segmentation", "Foundation Model"],
    "abstract": "We introduce the Segment Anything project: a new task, model, and dataset for image segmentation...",
    "pdfUrl": "https://arxiv.org/pdf/2304.02643",
    "imageUrl": "/mockup_thumb.jpg",
  },
]

def seed_data():
    with Session(engine) as session:
        print("Cleaning up old data...")
        # Delete old data to avoid duplicates/conflicts when re-seeding
        # Note: CASCADE will delete related PaperTag entries
        session.exec(text("TRUNCATE TABLE papers CASCADE"))
        session.exec(text("TRUNCATE TABLE tags CASCADE"))
        session.commit()
        
        # Pre-fetch or create tags
        tag_map = {}
        for p_data in papers_data:
            for t_name in p_data["tags"]:
                if t_name not in tag_map:
                    # Check DB (though we truncated, so it will be empty)
                    new_tag = Tag(name=t_name, description="")
                    session.add(new_tag)
                    session.flush() # to get ID
                    tag_map[t_name] = new_tag
        
        # Insert Papers
        for p_data in papers_data:
            print(f"Adding paper: {p_data['title']}")
            
            # Map year to date
            pub_date = datetime(p_data["year"], 1, 1)
            
            # Create Paper
            paper = Paper(
                title=p_data["title"],
                short=p_data["abstract"],
                authors=p_data["authors"],
                published_at=pub_date,
                image_url=p_data["imageUrl"],
                raw_url=p_data["pdfUrl"],
                source=Site.arxiv, # Default to arxiv for now as most are
                created_at=utcnow()
            )
            session.add(paper)
            session.flush() # get ID

            # Link Tags
            for t_name in p_data["tags"]:
                tag = tag_map[t_name]
                paper_tag = PaperTag(paper_id=paper.id, tag_id=tag.id)
                session.add(paper_tag)
                # Update tag count
                tag.count += 1
                session.add(tag)

        session.commit()
        print("Done seeding data.")

if __name__ == "__main__":
    seed_data()
