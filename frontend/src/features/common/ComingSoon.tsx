// Placeholder for modules scheduled in a later phase (keeps navigation complete).
import { Result, Tag } from "antd";
import PageContainer from "@/components/PageContainer";

interface Props {
  title: string;
  phase?: number;
  description?: string;
}

export default function ComingSoon({ title, phase = 2, description }: Props) {
  return (
    <PageContainer title={title} description={description}>
      <Result
        status="info"
        title={<span>{title} <Tag color="blue">Phase {phase}</Tag></span>}
        subTitle="该模块将在后续阶段实现。当前为 MVP 骨架，导航已就位。"
      />
    </PageContainer>
  );
}
