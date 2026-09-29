import { moreFeatures } from '../content/site';
import Reveal from './Reveal';
import './MoreFeatures.css';

/** Secondary feature inventory: a quiet hairline list. Owned by the website agent. */
export default function MoreFeatures() {
  return (
    <section className="section more" aria-labelledby="more-title">
      <div className="container more-inner">
        <Reveal className="more-head">
          <p className="eyebrow">{moreFeatures.eyebrow}</p>
          <h2 id="more-title" className="more-title">
            {moreFeatures.title}
          </h2>
        </Reveal>

        <ul className="more-list">
          {moreFeatures.items.map((item) => (
            <li key={item.title} className="more-item">
              <h3 className="more-name">{item.title}</h3>
              <div className="more-detail">
                <p className="more-body">{item.body}</p>
                {item.example && (
                  <p className="more-example">
                    <code>{item.example}</code>
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
